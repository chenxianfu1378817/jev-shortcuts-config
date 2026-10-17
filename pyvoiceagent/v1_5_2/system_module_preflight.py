"""V1.5 development helper: fail closed before calling system Shortcuts."""

SYSTEM_MODULES = {
    'apple_notes.create': 'PYAgentNotes',
    'calendar.create': 'PYAgentCalendar',
}


def verified_target(route, registry):
    """Allow a system route only after an explicit on-device verification."""
    required = SYSTEM_MODULES.get(route)
    if not required or not isinstance(registry, dict):
        return None
    modules = registry.get('modules')
    if not isinstance(modules, dict):
        return None
    entry = modules.get(route)
    if not isinstance(entry, dict):
        return None
    if entry.get('name') == required and entry.get('verified') is True:
        return required
    return None


def available_tools(catalog, registry):
    """Filter the AI tool list so unconfigured routes aren't suggested."""
    return {
        key: value for key, value in catalog.items()
        if key not in SYSTEM_MODULES or verified_target(key, registry)
    }


def preflight(route, registry):
    """Never dispatch unknown system writes; unsupported -> no side effects."""
    if route in SYSTEM_MODULES and not verified_target(route, registry):
        return {
            'status': 'unavailable',
            'side_effect': False,
            'needs_manual_review': False,
            'message': '系统模块尚未完成安装与验证，未发送创建请求：' + route,
        }
    return {'status': 'ready', 'side_effect': False, 'needs_manual_review': False}
