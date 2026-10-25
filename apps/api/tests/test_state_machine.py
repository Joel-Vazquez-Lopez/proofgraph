import pytest
from packages.shared_schemas.models import InvestigationState
from app.services.state_machine import InvestigationStateMachine, InvalidStateTransitionError


def test_valid_state_transitions():
    # CREATED -> INTAKE_COMPLETE
    s1 = InvestigationStateMachine.transition(InvestigationState.CREATED, InvestigationState.INTAKE_COMPLETE)
    assert s1 == InvestigationState.INTAKE_COMPLETE

    # INTAKE_COMPLETE -> INVESTIGATING
    s2 = InvestigationStateMachine.transition(s1, InvestigationState.INVESTIGATING)
    assert s2 == InvestigationState.INVESTIGATING

    # INVESTIGATING -> AWAITING_EVIDENCE
    s3 = InvestigationStateMachine.transition(s2, InvestigationState.AWAITING_EVIDENCE)
    assert s3 == InvestigationState.AWAITING_EVIDENCE

    # AWAITING_EVIDENCE -> INVESTIGATING
    s4 = InvestigationStateMachine.transition(s3, InvestigationState.INVESTIGATING)
    assert s4 == InvestigationState.INVESTIGATING

    # INVESTIGATING -> DECISION_READY
    s5 = InvestigationStateMachine.transition(s4, InvestigationState.DECISION_READY)
    assert s5 == InvestigationState.DECISION_READY

    # DECISION_READY -> CLOSED
    s6 = InvestigationStateMachine.transition(s5, InvestigationState.CLOSED)
    assert s6 == InvestigationState.CLOSED


def test_invalid_state_transitions():
    # Cannot jump directly from CREATED to DECISION_READY
    with pytest.raises(InvalidStateTransitionError):
        InvestigationStateMachine.transition(InvestigationState.CREATED, InvestigationState.DECISION_READY)

    # Cannot transition out of CLOSED
    with pytest.raises(InvalidStateTransitionError):
        InvestigationStateMachine.transition(InvestigationState.CLOSED, InvestigationState.INVESTIGATING)


def test_idempotent_transition():
    s = InvestigationStateMachine.transition(InvestigationState.INVESTIGATING, InvestigationState.INVESTIGATING)
    assert s == InvestigationState.INVESTIGATING
