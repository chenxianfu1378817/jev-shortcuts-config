# -*- coding: utf-8 -*-
"""V1.8.4: resumable, bounded on-device clarification without replaying writes."""
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("core184", ROOT / "agent_core_1_8_4.py")
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


def action(tool="text.respond", title="", text="按要求完成"):
    return {"tool": tool, "reason": "测试", "text": text, "title": title,
            "datetime": "", "end_datetime": "", "notes": "", "shortcut_id": ""}


def plan(actions=None, question=""):
    return {"actions": list(actions or []), "question": question}


class Interactive184Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path_patch = patch.object(agent, "STATE_PATH", str(Path(temporary.name) / "state.json"))
        path_patch.start()
        self.addCleanup(path_patch.stop)
        self.state = {"id": "test-184", "goal": "帮我整理明天的工作",
                      "created": "2026-11-03T10:00:00+08:00",
                      "steps": 0, "events": [], "pending": None, "status": "ready"}
        agent.put_state(self.state)

    def available(self):
        return patch.object(agent, "available_tool_catalog",
                            return_value={"text.respond": "display", "calendar.create": "calendar"})

    def test_version_and_explicit_execution_priority(self):
        self.assertEqual(agent.VERSION, "1.8.4-deepseek-flash")
        self.assertEqual(agent.MAX_CLARIFICATION_ROUNDS, 4)
        self.assertIn("信息齐全时直接给出 actions", agent.ONE_SHOT_POLICY)
        self.assertIn("禁止用 question 询问是否继续", agent.ONE_SHOT_POLICY)

    def test_complete_plan_does_not_ask(self):
        final = plan([action()])
        with self.available(), patch.object(agent, "_deepseek_request", return_value=final) as ai,\
             patch.object(agent, "_ask_clarification") as ask,\
             patch.object(agent, "execute_planned_actions", return_value=self.state) as execute:
            agent.plan_once(self.state)
        self.assertEqual(ai.call_count, 1)
        ask.assert_not_called()
        execute.assert_called_once()

    def test_question_answer_then_same_original_goal_executes(self):
        with self.available(),\
             patch.object(agent, "_deepseek_request", side_effect=[
                 plan(question="会议几点开始？"), plan([action(text="已获得会议时间")])
             ]) as ai,\
             patch.object(agent, "_ask_clarification", return_value="下午三点") as ask,\
             patch.object(agent, "execute_planned_actions", return_value=self.state) as execute:
            agent.plan_once(self.state)
        ask.assert_called_once_with("会议几点开始？")
        execute.assert_called_once()
        self.assertEqual(self.state["clarify_history"],
                         [{"question": "会议几点开始？", "answer": "下午三点"}])
        payload = json.loads(ai.call_args_list[-1].args[0][-1]["content"])
        self.assertEqual(payload["goal"], self.state["goal"])
        self.assertEqual(payload["clarifications"], self.state["clarify_history"])
        self.assertEqual(self.state["status"], "ready")

    def test_two_rounds_until_plan_ready(self):
        with self.available(),\
             patch.object(agent, "_deepseek_request", side_effect=[
                 plan(question="哪天？"), plan(question="几点？"), plan([action()])
             ]) as ai,\
             patch.object(agent, "_ask_clarification", side_effect=["周五", "下午两点"]),\
             patch.object(agent, "execute_planned_actions", return_value=self.state) as execute:
            agent.plan_once(self.state)
        self.assertEqual(ai.call_count, 3)
        self.assertEqual(len(self.state["clarify_history"]), 2)
        execute.assert_called_once()

    def test_defer_and_resume_later_by_answer(self):
        with self.available(),\
             patch.object(agent, "_deepseek_request", return_value=plan(question="请提供时间")),\
             patch.object(agent, "_ask_clarification", return_value=None),\
             patch.object(agent, "execute_planned_actions") as execute:
            agent.plan_once(self.state)
            execute.assert_not_called()
        self.assertEqual(agent.get_state()["status"], "needs_input")
        with self.available(),\
             patch.object(agent, "api_key", return_value="test-key"),\
             patch.object(agent, "_deepseek_request", return_value=plan([action()])),\
             patch.object(agent, "execute_planned_actions", side_effect=lambda s: s) as execute:
            result = agent.resume_clarification(agent.get_state(), initial_answer="明天14点")
        execute.assert_called_once()
        self.assertEqual(result["clarify_history"][0]["answer"], "明天14点")

    def test_replan_network_failure_is_retriable_without_reasking(self):
        with self.available(),\
             patch.object(agent, "_deepseek_request", side_effect=[
                 plan(question="缺少时间"), RuntimeError("network down"), plan([action()])
             ]) as ai,\
             patch.object(agent, "_ask_clarification", return_value="9点") as ask,\
             patch.object(agent, "api_key", return_value="test-key"),\
             patch.object(agent, "execute_planned_actions", return_value=self.state) as execute:
            agent.plan_once(self.state)
            self.assertEqual(agent.get_state()["status"], "replan_pending")
            self.assertEqual(len(agent.get_state()["clarify_history"]), 1)
            agent.resume_clarification(agent.get_state())
        self.assertEqual(ai.call_count, 3)
        ask.assert_called_once()
        execute.assert_called_once()

    def test_four_round_cap_prevents_endless_loop(self):
        self.state["clarify_history"] = [{"question": "q", "answer": "a"}] * 4
        with patch.object(agent, "_ask_clarification") as ask,\
             patch.object(agent, "_request_clarification_plan") as ai:
            out = agent._resolve_clarifications(self.state, plan(question="第五次追问"), {})
        self.assertIsNone(out)
        self.assertEqual(self.state["status"], "paused")
        ask.assert_not_called()
        ai.assert_not_called()

    def test_new_voice_utterance_is_intercepted_before_local_writes(self):
        self.state["status"] = "needs_input"
        self.state["clarify_question"] = "几点？"
        agent.put_state(self.state)
        with patch.object(agent, "prompt_alert", return_value=True),\
             patch.object(agent, "resume_clarification", return_value={"status": "ready"}) as resume,\
             patch.object(agent, "_cc_trigger", side_effect=AssertionError("must not trigger new write")),\
             patch.object(agent, "_maybe_auto_work_plan", side_effect=AssertionError("must not create reminder")):
            out = agent.start_new("明天整理客户资料")
        self.assertEqual(out["status"], "ready")
        self.assertEqual(resume.call_args.kwargs["initial_answer"], "明天整理客户资料")

    def test_changed_clipboard_not_resent_to_cloud(self):
        self.state["status"] = "replan_pending"
        self.state["clarify_clipboard_sha256"] = "0" * 64
        clipboard = types.SimpleNamespace(get=lambda: "different content")
        with self.available(), patch.object(agent, "_deepseek_request") as ai,\
             patch.dict(sys.modules, {"clipboard": clipboard}):
            out = agent._request_clarification_plan(self.state, {"text.respond": "display"})
        self.assertIsNone(out)
        self.assertIn("剪贴板内容已经变化", self.state["error"])
        ai.assert_not_called()

    def test_write_confirmation_still_required(self):
        event = action("calendar.create", title="测试会议", text="")
        event["datetime"] = "2026-12-03T14:00:00+08:00"
        event["end_datetime"] = "2026-12-03T15:00:00+08:00"
        with self.available(),\
             patch.object(agent, "_deepseek_request", return_value=plan([event])),\
             patch.object(agent, "prompt_alert", return_value=False) as ask,\
             patch.object(agent, "execute_planned_actions") as execute:
            agent.plan_once(self.state)
        self.assertEqual(self.state["status"], "paused")
        ask.assert_called_once()
        execute.assert_not_called()

    def test_voice_text_later_selector(self):
        dlg = types.SimpleNamespace(alert=lambda *a, **kw: 1)
        with patch.dict(sys.modules, {"dialogs": dlg}),\
             patch.object(agent, "input_voice", return_value="三点"):
            self.assertEqual(agent._ask_clarification("几点？"), "三点")
        dlg = types.SimpleNamespace(alert=lambda *a, **kw: 2)
        with patch.dict(sys.modules, {"dialogs": dlg}),\
             patch.object(agent, "ask_text", return_value="四点"):
            self.assertEqual(agent._ask_clarification("几点？"), "四点")
        dlg = types.SimpleNamespace(alert=lambda *a, **kw: 3)
        with patch.dict(sys.modules, {"dialogs": dlg}):
            self.assertIsNone(agent._ask_clarification("几点？"))


if __name__ == "__main__":
    unittest.main()
