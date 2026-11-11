# PYVoiceAgent V3 — Architecture Decision Record (2026-11-12)

**Status: DRAFT / architecture only. NOT a mobile release.**  
**V2.3.x freeze:** Do not change `pyvoiceagent/manifest.json`, `PYVoiceAgent.py`, or users' `PYVoiceAgent_Data` from this branch. V2.3.9 failed to achieve same-iPhone stability; re-labelling an unverified version "stable" is prohibited.

## Reason for re-architecture

V2.3.4–V2.3.9 repeatedly crashed during microphone stop, text submit and history navigation despite several WebView/native UI rewrites. Individual CI unit tests cannot validate iOS 27 + Pythonista runtime, native Objective-C operations, UIKit lifetimes, keyboard interactions, or device-specific memory faults. Without a symbolicated .ips crash report, do not assert one unique root cause.

The 25 numbered `src/*.py` files are **build-time source fragments**, not independently imported/runtime-isolated feature modules. Build concatenates their code and relies on globals and monkey patches. The V2.3.9 `_NativeChatShell` still subclasses the old `_ChatShell`, which handles persistence, events, task dispatch and UI callbacks. The History button starts a background reader and calls UI marshaling from that thread. Settings disappeared in the native UI replacement. These are demonstrable design regressions, not just possible keyboard issues.

## Recommended platform decomposition

**Immediately:** keep Apple's Shortcuts as the verified interactive/permissioned system-action interface; retain the current Pythonista entry only as an optional, isolated one-shot command-line helper, **not a persistent interactive chat UI**. Do not repeatedly trigger crashing paths or create real reminders/calendar events to test.

**Core:** write an independent Python package with ordinary imports and explicit interfaces. It must execute and be tested under macOS/Windows/Linux without importing Pythonista `ui`, `sound`, `speech`, `objc_util`, or any system SDK. Use dependency injection for all platform services.

**Rich conversation frontend (separate decision):**
- Long-term first choice for reliable, full-featured iPhone chat: a **native SwiftUI** thin client integrating iOS SDK interfaces and Shortcuts/App Intents where available. **Trade-off:** requires signing/installing a real iOS app (TestFlight/App Store or development provisioning), and each system permission follows iOS restrictions; no promise of unrestricted background operation.
- Installation-light alternative: offline-capable **PWA/Safari** frontend for chat and configuration, with an explicit authenticated network backend. iOS privileged actions **cannot** execute automatically from a PWA; each must be handed to user-approved Shortcuts/native integrations. Private app state and API keys require secure storage and a deliberate backup/retention plan.
- Short-term fallback: **Shortcuts + limited Pythonista one-shot tasks** for device automation, without maintaining a persistent UI session.

Do **not** replicate the V2 architecture in either new frontend. First prove the engine, contracts and data protection in isolation.

## Proposed package layout (actual imports, not concatenated files)

```
pyvoiceagent_v3/
  core/
    models.py              # typed commands, events and outcomes
    dispatcher.py          # one incoming request -> one durable task ID
    state_machine.py       # queued/running/waiting/needs_review/finished/failed
    policies.py            # read/write risk, confirmations, permissions
    dedupe.py              # idempotency keys and re-entrancy guard
  services/
    llm.py                 # DeepSeek request/retry/timeout adapter
    conversation.py        # explicit context/token limits
    shortcuts.py           # tool registry, validated parameters & receipts
    calendar.py
    reminders.py
    contacts.py
    clipboard.py
    maps.py
    market_bu.py
    history.py             # read-only queries, isolated parsing
    settings.py            # appearance, version, account preferences
  storage/
    sqlite_store.py        # SQLite transaction boundary and migrations
    migrations/
  adapters/
    ios_shortcuts.py       # explicit native handoff, not auto-background
    pythonista_cli.py      # optional, no persistent ui.View/WebView
    server_api.py          # optional authenticated, audited backend
  contracts/
    command_v1.json
    event_v1.json
    tool_result_v1.json
  tests/
    unit/
    contract/
    failure_injection/
    regression/
```

## Non-negotiable runtime constraints

1. **Single task coordinator**: one task ID, one state machine, idempotent writes; do not spawn ad hoc threads per tap.
2. **UI is a consumer of immutable events**. It never reads/write task JSON, uses no global monkey-patched functions, and never calls external service code in a UI callback.
3. **All UI mutation on the platform's UI thread**. Worker threads never touch UIKit view properties; native dialogs are invoked only through documented main-thread presentation.
4. **History reading is read-only**, paged, bounded, and tolerant of invalid records; never perform directory scans or file parsing in a UI button callback.
5. **Settings/menu contract** covers AI API credentials, all eight color themes, light/dark/system, installed tool modules, shortcut manager, online update status, history, diagnostics and app exit. No feature removal without explicit request.
6. **Data remains user-owned**: preserve existing local history, shortcuts, settings, API keys and deduplication ledgers. Migration uses backups, strict versioned schema, dry-run before mutation and rollback.
7. **Security**: no API key or transcript in logs; explicit permission for sending data to an LLM; no secret in source/git; no silent retries for calendar/reminder writes.
8. **Updates**: do not touch `main` manifest until device validation; immutable releases with digest checks, minimum version, rollback and clear changelog.
9. **Prove failures**: offline, timeout, invalid API, broken JSON, repeated tap, keyboard composition, view dismissal, backgrounding, restart during a pending write, and history corruption must all have automated tests.
10. **iPhone validation is separate** from CI. A pass requires *same-device* cold launches, navigation, no-op inputs, text submission, history, settings, voice handoff, network failure, interrupted tasks, repeat commands and permission handling. If SIGSEGV persists, gather the anonymized iOS .ips stack before coding another workaround.

## Work sequence and hard release gates

A. Freeze V2.3.9; capture exact crash conditions, version, and iOS `.ips` from Settings -> Privacy & Security -> Analytics & Improvements -> Analytics Data if available. Never ask user to expose private prompts/API keys.

B. Implement pure Python V3 core, database adapter, tool contracts, deterministic error injection and migration reader **in a separate folder and branch**. No UI/deploy yet.

C. Prototype independent frontend(s); test all navigation including Settings, History and Exit **without AI or tools**. Pass device validation before connecting real services.

D. Connect one read-only tool, then a read-only LLM request, then permissioned writes individually. Verify no duplicate task IDs/side effects.

E. Ship V3 only after device acceptance and verified migration/rollback; preserve V2 as unchanged archival fallback.

## Explicitly not completed

This ADR is a design and branching decision only. No V3 core, phone frontend, audio, data migration, device test or release has been implemented. There is **no new update** for the iPhone.
