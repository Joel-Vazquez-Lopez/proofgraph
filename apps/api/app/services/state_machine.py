from typing import Set, Dict
from packages.shared_schemas.models import InvestigationState


class InvalidStateTransitionError(Exception):
    def __init__(self, current_state: InvestigationState, target_state: InvestigationState, reason: str = ""):
        self.current_state = current_state
        self.target_state = target_state
        self.reason = reason
        super().__init__(
            f"Illegal state transition from {current_state.value} to {target_state.value}. {reason}".strip()
        )


class InvestigationStateMachine:
    """
    Deterministic state machine governing dispute investigation progression.
    The AI model is strictly prohibited from bypassing this machine.
    """

    ALLOWED_TRANSITIONS: Dict[InvestigationState, Set[InvestigationState]] = {
        InvestigationState.CREATED: {
            InvestigationState.INTAKE_COMPLETE,
        },
        InvestigationState.INTAKE_COMPLETE: {
            InvestigationState.INVESTIGATING,
        },
        InvestigationState.INVESTIGATING: {
            InvestigationState.AWAITING_EVIDENCE,
            InvestigationState.DECISION_READY,
            InvestigationState.REVIEW_REQUIRED,
        },
        InvestigationState.AWAITING_EVIDENCE: {
            InvestigationState.INVESTIGATING,
            InvestigationState.REVIEW_REQUIRED,
        },
        InvestigationState.REVIEW_REQUIRED: {
            InvestigationState.INVESTIGATING,
            InvestigationState.CLOSED,
        },
        InvestigationState.DECISION_READY: {
            InvestigationState.INVESTIGATING,  # If new contradictory evidence arrives
            InvestigationState.CLOSED,
        },
        InvestigationState.CLOSED: set(),  # Terminal state
    }

    @classmethod
    def can_transition(cls, current: InvestigationState, target: InvestigationState) -> bool:
        allowed = cls.ALLOWED_TRANSITIONS.get(current, set())
        return target in allowed

    @classmethod
    def transition(cls, current: InvestigationState, target: InvestigationState, reason: str = "") -> InvestigationState:
        if current == target:
            return current
        if not cls.can_transition(current, target):
            raise InvalidStateTransitionError(
                current_state=current,
                target_state=target,
                reason=reason or f"Valid transitions from {current.value} are: {[s.value for s in cls.ALLOWED_TRANSITIONS.get(current, set())]}"
            )
        return target
