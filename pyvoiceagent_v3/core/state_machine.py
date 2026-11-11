"""The complete V3 task lifecycle and state transitions."""
from .models import InvalidTransition

TRANSITIONS = {
    'queued': frozenset(('running', 'completed', 'waiting_consent',
                          'waiting_confirmation', 'failed', 'cancelled')),
    'waiting_consent': frozenset(('running', 'cancelled')),
    'waiting_confirmation': frozenset(('handoff_ready', 'cancelled')),
    'running': frozenset(('completed', 'failed', 'needs_review')),
    'handoff_ready': frozenset(('needs_review', 'cancelled')),
    'needs_review': frozenset(('cancelled',)),
    'completed': frozenset(),
    'failed': frozenset(),
    'cancelled': frozenset(),
}


def check_transition(old, new):
    if old not in TRANSITIONS or new not in TRANSITIONS[old]:
        raise InvalidTransition('Illegal task state transition: {} -> {}'.format(old, new))
    return True
