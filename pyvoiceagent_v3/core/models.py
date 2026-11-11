"""Typed, immutable values shared across adapters (no iOS imports)."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    status: str
    message: str
    fresh: bool = True
    confirmation_required: bool = False
    action: Optional[dict] = None

    def to_dict(self):
        return {
            'task_id': self.task_id, 'status': self.status,
            'message': self.message, 'fresh': self.fresh,
            'confirmation_required': self.confirmation_required,
            'action': dict(self.action) if self.action else None,
        }


class InputError(ValueError):
    """Rejected before any new side effects are allowed."""


class InvalidTransition(ValueError):
    """The persisted task has already moved out of the expected stage."""
