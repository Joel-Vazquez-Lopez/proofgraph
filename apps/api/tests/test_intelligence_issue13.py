"""Issue #13: distinguish evidence sufficiency, provenance and policy behavior.

Tests are contract-oriented rather than checking the old five scenario labels.
"""
import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.config import settings
from app.models.db_models import Base, engine, init_db
from app.services.evidence_graph import EvidenceGraph
from app.services.evaluator import DecisionReadinessEvaluator
from app.services.nbe_policy import HeuristicNBEPolicy
from app.services.nbe_adaptive import HypothesisDiscriminationPolicy
from packages.shared_schemas.models import (
    DisputeCategory as C, NodeType as N, EdgeType as E,
    EvidenceOrigin as O, EvidenceVerificationStatus as V, ActionType as A,
)


def _graph():
    g = EvidenceGraph("issue13")
    tx = g.add_node(N.TRANSACTION, "Payment", {
        "transaction_id": "pay-a", "amount": 40, "currency": "USD", "order_id": "ord-1"
    }, "PAYPAL", node_id="tx-a", origin=O.VERIFIED_EXTERNAL, verification_status=V.VERIFIED)
    order = g.add_node(N.ORDER, "Order", {
        "destination_address": {"postal_code": "11590"}, "item_name": "Headphones"
    }, "MERCHANT", node_id="ord-1", origin=O.USER_SUBMITTED)
    shipment = g.add_node(N.SHIPMENT, "Shipment", {"tracking_number": "TR-1"},
                          "MERCHANT", node_id="ship-1", origin=O.USER_SUBMITTED)
    g.add_edge(order.id, shipment.id, E.RELATES_TO, "order shipment")
    claim = g.add_node(N.CLAIM, "Nonreceipt", {"party": "BUYER"},
                       "BUYER", node_id="claim-1", origin=O.USER_SUBMITTED)
    return g, shipment


def _scan(g, shipment, zip_code, *, origin=O.VERIFIED_EXTERNAL,
          status="DELIVERED", verified=True, node_id="scan-1"):
    observation = g.add_node(
        N.OBSERVATION, "Carrier status", {
            "status": status, "delivered_to_address": {"postal_code": zip_code}
        }, "CARRIER_SERVICE", node_id=node_id, origin=origin,
        verification_status=V.VERIFIED if verified else V.UNVERIFIED
    )
    g.add_edge(observation.id, shipment.id, E.DERIVED_FROM, "carrier shipment relationship")
    return observation


@pytest.mark.parametrize("policy", [HeuristicNBEPolicy, HypothesisDiscriminationPolicy])
def test_inr_matching_delivery_still_requires_handoff_not_decision(policy):
    g, shipment = _graph()
    _scan(g, shipment, "11590")
    readiness = DecisionReadinessEvaluator.evaluate(C.ITEM_NOT_RECEIVED, g)
    assert not readiness.is_decision_ready
    assert any("non-receipt" in x.lower() for x in readiness.missing_requirements)
    decision = policy().evaluate_candidates(C.ITEM_NOT_RECEIVED, g, readiness)
    assert decision.chosen_action.action_type == A.REQUEST_PROOF_OF_DELIVERY


@pytest.mark.parametrize("policy", [HeuristicNBEPolicy, HypothesisDiscriminationPolicy])
def test_inr_unverified_carrier_claim_not_accepted_or_confused_with_scan(policy):
    g, shipment = _graph()
    _scan(g, shipment, "11590", origin=O.USER_SUBMITTED)
    readiness = DecisionReadinessEvaluator.evaluate(C.ITEM_NOT_RECEIVED, g)
    assert not readiness.is_decision_ready
    assert not any("Carrier verified delivery" in x for x in readiness.satisfied_requirements)
    decision = policy().evaluate_candidates(C.ITEM_NOT_RECEIVED, g, readiness)
    assert decision.chosen_action.action_type != A.REQUEST_PROOF_OF_DELIVERY


@pytest.mark.parametrize("policy", [HeuristicNBEPolicy, HypothesisDiscriminationPolicy])
def test_inr_implicit_wrong_address_blocks_readiness_and_targets_discrepancy(policy):
    g, shipment = _graph()
    _scan(g, shipment, "90210")
    readiness = DecisionReadinessEvaluator.evaluate(C.ITEM_NOT_RECEIVED, g)
    assert not readiness.is_decision_ready
    assert readiness.requires_escalation
    assert "scan-1" in " ".join(readiness.active_contradictions)
    decision = policy().evaluate_candidates(C.ITEM_NOT_RECEIVED, g, readiness)
    assert decision.chosen_action.action_type == A.REQUEST_BUYER_CLARIFICATION


@pytest.mark.parametrize("policy", [HeuristicNBEPolicy, HypothesisDiscriminationPolicy])
def test_inr_disagreeing_reports_are_never_decision_ready(policy):
    g, shipment = _graph()
    _scan(g, shipment, "11590")
    _scan(g, shipment, "90210", node_id="scan-2")
    readiness = DecisionReadinessEvaluator.evaluate(C.ITEM_NOT_RECEIVED, g)
    assert not readiness.is_decision_ready
    assert readiness.requires_escalation
    assert "scan-2" in " ".join(readiness.active_contradictions)
    action = policy().evaluate_candidates(C.ITEM_NOT_RECEIVED, g, readiness).chosen_action
    assert action is not None and action.action_type == A.REQUEST_BUYER_CLARIFICATION


def test_fixture_delivery_is_not_described_as_independent_verification():
    g, shipment = _graph()
    _scan(g, shipment, "11590", origin=O.SYNTHETIC_FIXTURE)
    readiness = DecisionReadinessEvaluator.evaluate(C.ITEM_NOT_RECEIVED, g)
    assert "simulated" in " ".join(readiness.satisfied_requirements).lower()
    assert "not independent" in " ".join(readiness.satisfied_requirements).lower()


def test_unrelated_uploaded_signature_does_not_satisfy_buyer_nonreceipt():
    g, shipment = _graph()
    _scan(g, shipment, "11590")
    uploaded = g.add_node(N.EVIDENCE_ITEM, "signed receipt", {"kind": "signature_record"},
                          "MERCHANT", origin=O.USER_SUBMITTED,
                          verification_status=V.VERIFIED)
    g.add_edge(uploaded.id, shipment.id, E.RELATES_TO, "merchant submission")
    readiness = DecisionReadinessEvaluator.evaluate(C.ITEM_NOT_RECEIVED, g)
    assert not readiness.is_decision_ready
    assert any("non-receipt" in m.lower() for m in readiness.missing_requirements)


def test_snad_image_only_is_incomplete_until_listing_submitted():
    g, _ = _graph()
    image = g.add_node(N.EVIDENCE_ITEM, "Photograph", {"mime_type": "image/png"},
                       "BUYER_UPLOAD", origin=O.USER_SUBMITTED)
    readiness = DecisionReadinessEvaluator.evaluate(C.SIGNIFICANTLY_NOT_AS_DESCRIBED, g)
    assert not readiness.is_decision_ready
    assert any("listing" in m.lower() for m in readiness.missing_requirements)
    action = HeuristicNBEPolicy().evaluate_candidates(
        C.SIGNIFICANTLY_NOT_AS_DESCRIBED, g, readiness
    ).chosen_action
    assert action.action_id == "act_merchant_listing"
    g.add_node(N.EVIDENCE_ITEM, "Original listing", {"kind": "merchant_listing"},
               "MERCHANT_UPLOAD", origin=O.USER_SUBMITTED, node_id="listing")
    readiness = DecisionReadinessEvaluator.evaluate(C.SIGNIFICANTLY_NOT_AS_DESCRIBED, g)
    assert readiness.is_decision_ready
    assert "not proof" in readiness.rationale.lower() or "not a finding" in readiness.rationale.lower()
    g.add_edge(image.id, "listing", E.CONTRADICTS, "reported damage conflicts with listed new condition")
    assert not DecisionReadinessEvaluator.evaluate(C.SIGNIFICANTLY_NOT_AS_DESCRIBED, g).is_decision_ready


def test_duplicate_two_unverified_payment_assertions_never_close():
    g, _ = _graph()
    g.add_node(N.TRANSACTION, "Seller assertion", {
        "transaction_id": "pay-b", "order_id": "ord-1",
        "amount": 40, "currency": "USD"
    }, "MERCHANT", origin=O.USER_SUBMITTED, verification_status=V.VERIFIED)
    ready = DecisionReadinessEvaluator.evaluate(C.DUPLICATE_TRANSACTION, g)
    assert not ready.is_decision_ready
    action = HeuristicNBEPolicy().evaluate_candidates(C.DUPLICATE_TRANSACTION, g, ready).chosen_action
    assert action.action_id == "act_request_transaction_records"


def test_duplicate_reconciled_authoritative_records_change_readiness_and_action():
    g, _ = _graph()
    second = g.add_node(N.TRANSACTION, "Payment two", {
        "transaction_id": "pay-b", "order_id": "ord-1",
        "amount": 40, "currency": "USD"
    }, "PAYPAL", origin=O.VERIFIED_EXTERNAL, verification_status=V.VERIFIED)
    readiness = DecisionReadinessEvaluator.evaluate(C.DUPLICATE_TRANSACTION, g)
    assert readiness.is_decision_ready
    decision = HeuristicNBEPolicy().evaluate_candidates(C.DUPLICATE_TRANSACTION, g, readiness)
    assert decision.chosen_action is None
    g.add_edge(second.id, "tx-a", E.CONTRADICTS, "provider records disagree on parent order")
    assert not DecisionReadinessEvaluator.evaluate(C.DUPLICATE_TRANSACTION, g).is_decision_ready


def test_duplicate_two_payment_ids_without_order_linkage_not_ready():
    g, _ = _graph()
    g.add_node(N.TRANSACTION, "Payment two", {
        "transaction_id": "pay-b", "amount": 40, "currency": "USD"
    }, "PAYPAL", origin=O.VERIFIED_EXTERNAL, verification_status=V.VERIFIED)
    readiness = DecisionReadinessEvaluator.evaluate(C.DUPLICATE_TRANSACTION, g)
    assert not readiness.is_decision_ready
    assert "same original order" in " ".join(readiness.missing_requirements)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "NBE_POLICY_TYPE", "heuristic")
    Base.metadata.drop_all(bind=engine)
    init_db()
    return TestClient(app)


def _image():
    buffer = io.BytesIO()
    Image.new("RGB", (5, 5)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def test_snad_api_moves_from_photo_request_to_listing_then_review(client):
    case = "PP-D-SNAD-3012"
    initial = client.get(f"/api/v1/disputes/{case}").json()
    assert initial["current_policy_decision"]["chosen_action"]["action_id"] == "act_buyer_condition_photo"
    photo = client.post(f"/api/v1/disputes/{case}/evidence", json={
        "action_id": "act_buyer_condition_photo", "submitter_role": "BUYER",
        "file_data_base64": _image(), "file_name": "damage.png", "mime_type": "image/png"
    })
    assert photo.status_code == 200, photo.text
    detail = client.get(f"/api/v1/disputes/{case}").json()
    assert detail["current_policy_decision"]["chosen_action"]["action_id"] == "act_merchant_listing"
    assert detail["readiness"]["is_decision_ready"] is False
    listing_bytes = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"
    listing = client.post(f"/api/v1/disputes/{case}/evidence", json={
        "action_id": "act_merchant_listing", "submitter_role": "MERCHANT",
        "file_data_base64": base64.b64encode(listing_bytes).decode(),
        "file_name": "original_listing.pdf", "mime_type": "application/pdf"
    })
    assert listing.status_code == 200, listing.text
    detail = client.get(f"/api/v1/disputes/{case}").json()
    assert detail["readiness"]["is_decision_ready"] is True
    assert detail["current_policy_decision"]["chosen_action"] is None
    assert any(n["content"].get("kind") == "merchant_listing"
               and n["verification_status"] == "UNVERIFIED"
               for n in detail["evidence_graph"]["nodes"])


def test_duplicate_api_upload_remains_unverified_and_escalates_after_request(client):
    case = "PP-D-DUP-4044"
    initial = client.get(f"/api/v1/disputes/{case}").json()
    assert initial["current_policy_decision"]["chosen_action"]["action_id"] == "act_request_transaction_records"
    uploaded = client.post(f"/api/v1/disputes/{case}/evidence", json={
        "action_id": "act_request_transaction_records", "submitter_role": "MERCHANT",
        "file_data_base64": base64.b64encode(b"%PDF-1.4\n%%EOF").decode(),
        "file_name": "payment_logs.pdf", "mime_type": "application/pdf"
    })
    assert uploaded.status_code == 200, uploaded.text
    detail = client.get(f"/api/v1/disputes/{case}").json()
    assert detail["readiness"]["is_decision_ready"] is False
    assert detail["current_policy_decision"]["chosen_action"]["action_type"] == "ESCALATE_HUMAN_REVIEW"
    assert all(n["verification_status"] != "VERIFIED"
               for n in detail["evidence_graph"]["nodes"] if n["type"] == "EVIDENCE_ITEM")


def test_discriminative_policy_separate_snad_baseline_and_inr_misdelivery(monkeypatch):
    monkeypatch.setattr(settings, "NBE_POLICY_TYPE", "discriminative")
    Base.metadata.drop_all(bind=engine)
    init_db()
    tc = TestClient(app)
    snag = tc.get("/api/v1/disputes/PP-D-SNAD-3012").json()
    assert snag["current_policy_decision"]["policy_name"] == "HeuristicNBEPolicy"
    wrong = tc.get("/api/v1/disputes/PP-D-INR-9923").json()
    assert wrong["current_policy_decision"]["policy_name"] == "HypothesisDiscriminationPolicy"
    assert wrong["current_policy_decision"]["chosen_action"]["action_id"] == "act_resolve_contradiction"
    assert not wrong["readiness"]["is_decision_ready"]
