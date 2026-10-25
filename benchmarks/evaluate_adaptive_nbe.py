#!/usr/bin/env python3
"""Independent, seeded policy-challenge suite (NOT training/validation accuracy).

A different fixture construction and oracle table from the five legacy A-E
scenarios. Labels describe *useful supported next actions*, not dispute winners.
This remains synthetic, non-held-out evaluation and cannot establish calibration.
"""
from dataclasses import dataclass
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from packages.shared_schemas.models import (
    DisputeCategory, EdgeType, EvidenceOrigin, EvidenceVerificationStatus, NodeType, ActionType,
)
from app.services.evidence_graph import EvidenceGraph
from app.services.evaluator import DecisionReadinessEvaluator
from app.services.nbe_policy import HeuristicNBEPolicy
from app.services.nbe_adaptive import HypothesisDiscriminationPolicy
from app.services.hypothesis_engine import assess_inr_hypotheses


@dataclass(frozen=True)
class Challenge:
    name: str
    acceptable: tuple[str, ...]
    unavailable: tuple[str, ...] = ()
    must_escalate: bool = False


# Independently specified action requirements (not read from policy implementation).
CHALLENGES = (
    Challenge("missing_tracking", ("act_merchant_tracking",)),
    Challenge("verified_matching_scan", ("act_request_signature_or_proof",)),
    Challenge("wrong_zip_without_edge", ("act_resolve_contradiction",)),
    Challenge("two_conflicting_scans", ("act_resolve_contradiction", "act_request_carrier_receipt")),
    Challenge("untrusted_seller_delivery_claim", ("act_carrier_lookup",)),
    Challenge("lookup_unavailable", ("act_request_carrier_receipt",), ("act_carrier_lookup",)),
    Challenge("lookup_attempted", ("act_request_carrier_receipt",)),
    Challenge("verification_paths_exhausted", ("act_escalate_human_review",), must_escalate=True),
    Challenge("contradiction_clarification_attempted", ("act_request_carrier_receipt",)),
    Challenge("contradiction_actions_exhausted", ("act_escalate_human_review",), must_escalate=True),
    Challenge("in_transit_awaiting_update", ("act_carrier_lookup",)),
    Challenge("ambiguous_multiple_shipments", ("act_escalate_human_review",), must_escalate=True),
    Challenge("simulated_matching_scan", ("act_request_signature_or_proof",)),
    Challenge("unmatched_without_order_zip", ("act_carrier_lookup", "act_request_carrier_receipt")),
    Challenge("unlinked_delivery_observation", ("act_carrier_lookup",)),
)


def build_challenge(challenge: Challenge, rng: random.Random, index: int):
    case_id = f"CHALLENGE-{challenge.name}-{index}"
    graph = EvidenceGraph(case_id)
    order_zip = f"{rng.randint(10000, 89999):05d}"
    other_zip = f"{rng.randint(10000, 89999):05d}"
    while other_zip == order_zip:
        other_zip = f"{rng.randint(10000, 89999):05d}"
    order = graph.add_node(
        NodeType.ORDER, f"Ordered {case_id}",
        {"destination_address": {"postal_code": "" if challenge.name == "unmatched_without_order_zip" else order_zip}},
        "MERCHANT_ERP", node_id=f"ord_{index}_{challenge.name}"
    )
    graph.add_node(NodeType.CLAIM, "Buyer denies receipt",
                   {"party": "BUYER"}, "BUYER", node_id=f"claim_{index}_{challenge.name}")
    shipment = None
    if challenge.name != "missing_tracking":
        shipment = graph.add_node(
            NodeType.SHIPMENT, f"Shipment {case_id}",
            {"tracking_number": f"T{index}{rng.randint(100000, 999999)}"},
            "MERCHANT_ERP", node_id=f"ship_{index}_{challenge.name}"
        )
        graph.add_edge(order.id, shipment.id, EdgeType.RELATES_TO, "fulfillment")

    def report(label, dest, *, status="DELIVERED", origin=EvidenceOrigin.VERIFIED_EXTERNAL,
               verified=True, linked=True):
        observation = graph.add_node(
            NodeType.OBSERVATION, label,
            {"status": status, "delivered_to_address": {"postal_code": dest}},
            "GATEWAY", node_id=f"obs_{index}_{challenge.name}_{label}",
            origin=origin,
            verification_status=(
                EvidenceVerificationStatus.VERIFIED if verified else EvidenceVerificationStatus.UNVERIFIED
            ),
        )
        if linked:
            graph.add_edge(observation.id, shipment.id, EdgeType.DERIVED_FROM, "carrier report")
        return observation

    def attempt(action):
        graph.add_node(
            NodeType.QUESTION, "Previously requested",
            {"action": {"action_id": action}},
            "INVESTIGATION_ENGINE", node_id=f"q_{action}"
        )

    name = challenge.name
    if name in ("verified_matching_scan", "simulated_matching_scan"):
        report("match", order_zip, origin=(
            EvidenceOrigin.SYNTHETIC_FIXTURE
            if name == "simulated_matching_scan" else EvidenceOrigin.VERIFIED_EXTERNAL
        ))
    elif name in ("wrong_zip_without_edge", "contradiction_clarification_attempted",
                  "contradiction_actions_exhausted"):
        report("wrong", other_zip)
    elif name in ("two_conflicting_scans",):
        report("right", order_zip)
        report("wrong", other_zip)
    elif name == "untrusted_seller_delivery_claim":
        report("merchant_claim", order_zip, origin=EvidenceOrigin.USER_SUBMITTED)
    elif name == "in_transit_awaiting_update":
        report("transit", "", status="IN_TRANSIT")
    elif name == "ambiguous_multiple_shipments":
        report("match", order_zip)
        graph.add_node(NodeType.SHIPMENT, "Additional package", {"tracking_number": "ANOTHER"}, "MERCHANT")
    elif name == "unmatched_without_order_zip":
        report("unknown_destination", order_zip)
    elif name == "unlinked_delivery_observation":
        report("unrelated_report", order_zip, linked=False)

    if name in ("lookup_attempted", "verification_paths_exhausted"):
        attempt("act_carrier_lookup")
    if name == "verification_paths_exhausted":
        attempt("act_request_carrier_receipt")
    if name in ("contradiction_clarification_attempted", "contradiction_actions_exhausted"):
        attempt("act_resolve_contradiction")
    if name == "contradiction_actions_exhausted":
        attempt("act_request_carrier_receipt")
    return graph


def choose(policy, graph):
    readiness = DecisionReadinessEvaluator.evaluate(DisputeCategory.ITEM_NOT_RECEIVED, graph)
    return policy.evaluate_candidates(DisputeCategory.ITEM_NOT_RECEIVED, graph, readiness)


def measure(challenge, graph, adaptive):
    availability = {action: False for action in challenge.unavailable}
    engine = (HypothesisDiscriminationPolicy(availability=availability)
              if adaptive else HeuristicNBEPolicy())
    # Each engine observes the *same snapshot*, action list, and verification
    # facts. Legacy heuristic has no availability input, so unavailable
    # recommendations are measured rather than masked.
    decision = choose(engine, graph)
    action = decision.chosen_action.action_id if decision.chosen_action else None
    useful = action in challenge.acceptable
    unavailable = action in challenge.unavailable
    questions = {
        q.content.get("action", {}).get("action_id")
        for q in graph.get_nodes_by_type(NodeType.QUESTION)
        if isinstance(q.content.get("action"), dict)
    }
    repeated = action in questions if action else False
    escalation = (action == "act_escalate_human_review") == challenge.must_escalate
    review = assess_inr_hypotheses(graph)
    # Conservative textual audit for an unsupported assertion by the policy:
    # an untrusted submitted scan must not be spoken of as a carrier report.
    selected_text = ((decision.chosen_action.description + " " +
                      decision.chosen_action.rationale).lower()
                     if decision.chosen_action else "")
    unsupported = int(
        review.evidence_basis == "NONE"
        and "carrier reports residence delivery" in selected_text
    )

    # Acquisition-attempt proxy: number of inquiries until the first useful
    # action could acquire relevant evidence; no outcome is fabricated.
    steps = 0 if action == "act_escalate_human_review" and useful else (1 if useful else 5)
    if not useful:
        # Model the impact of unsuccessful / irrelevant questions through real
        # graph QUESTION history. Stop at a fixed shared five-attempt budget.
        trial_graph = EvidenceGraph.from_data(graph.dispute_id, graph.to_data().model_dump())
        steps = 0
        for i in range(5):
            next_decision = choose(engine, trial_graph)
            next_action = next_decision.chosen_action.action_id if next_decision.chosen_action else None
            if next_action in challenge.acceptable:
                steps += 1
                break
            if next_action is None or next_action == "act_escalate_human_review":
                steps = 5
                break
            steps += 1
            trial_graph.add_node(
                NodeType.QUESTION, "Action yielded no discriminating evidence",
                {"action": {"action_id": next_action}}, "BENCHMARK",
                node_id=f"bench_attempt_{i}_{next_action}"
            )
        else:
            steps = 5
    return dict(action=action, useful=useful, unavailable=unavailable,
                repeated=repeated, escalation=escalation,
                unsupported=unsupported, steps=steps)


def evaluate(seed=7331, variants=4):
    rng = random.Random(seed)
    outcomes = []
    for variant in range(variants):
        for challenge in CHALLENGES:
            graph = build_challenge(challenge, rng, variant)
            new = measure(challenge, graph, True)
            old = measure(challenge, graph, False)
            outcomes.append((challenge.name, variant, new, old))
    return outcomes


def summarize(rows, label):
    results = [r[2] if label == "Adaptive" else r[3] for r in rows]
    n = len(results)
    return {
        "policy": label,
        "cases": n,
        "correct_useful_first": sum(x["useful"] for x in results),
        "unsupported_verification_claims": sum(x["unsupported"] for x in results),
        "repeated_actions": sum(x["repeated"] for x in results),
        "unavailable_actions": sum(x["unavailable"] for x in results),
        "correct_escalation_or_continue": sum(x["escalation"] for x in results),
        "mean_attempts_to_first_useful_action": round(sum(x["steps"] for x in results) / n, 3),
    }


if __name__ == "__main__":
    rows = evaluate()
    print("INDEPENDENT POLICY CHALLENGES: seeded perturbations, 15 templates x 4 = 60")
    print("Synthetic oracle actions specify useful evidence acquisition, not adjudication.")
    for label in ("Adaptive", "Heuristic"):
        print(summarize(rows, label))
    wins = sorted({name for name, _, new, old in rows if new["useful"] and not old["useful"]})
    losses = sorted({name for name, _, new, old in rows if old["useful"] and not new["useful"]})
    print("First-step improvements on:", wins)
    print("First-step regressions on:", losses)
    print("Example comparisons:")
    for name in ("missing_tracking", "verified_matching_scan", "wrong_zip_without_edge",
                 "two_conflicting_scans", "untrusted_seller_delivery_claim",
                 "verification_paths_exhausted", "in_transit_awaiting_update"):
        _, _, new, old = next(r for r in rows if r[0] == name)
        print(f"  {name}: new={new['action']} old={old['action']}")

