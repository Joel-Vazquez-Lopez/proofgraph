from __future__ import annotations
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class DisputeCategory(str, Enum):
    ITEM_NOT_RECEIVED = "ITEM_NOT_RECEIVED"
    SIGNIFICANTLY_NOT_AS_DESCRIBED = "SIGNIFICANTLY_NOT_AS_DESCRIBED"
    DUPLICATE_TRANSACTION = "DUPLICATE_TRANSACTION"
    INCORRECT_AMOUNT = "INCORRECT_AMOUNT"
    UNAUTHORIZED_TRANSACTION = "UNAUTHORIZED_TRANSACTION"


class InvestigationState(str, Enum):
    CREATED = "CREATED"
    INTAKE_COMPLETE = "INTAKE_COMPLETE"
    INVESTIGATING = "INVESTIGATING"
    AWAITING_EVIDENCE = "AWAITING_EVIDENCE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DECISION_READY = "DECISION_READY"
    CLOSED = "CLOSED"


class DataSourceType(str, Enum):
    PAYPAL_SANDBOX = "PAYPAL_SANDBOX"
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
    MERCHANT_ERP = "MERCHANT_ERP"
    BUYER_SUBMISSION = "BUYER_SUBMISSION"
    CARRIER_API = "CARRIER_API"


class NodeType(str, Enum):
    DISPUTE = "DISPUTE"
    CLAIM = "CLAIM"
    TRANSACTION = "TRANSACTION"
    ORDER = "ORDER"
    PRODUCT = "PRODUCT"
    SHIPMENT = "SHIPMENT"
    EVIDENCE_ITEM = "EVIDENCE_ITEM"
    OBSERVATION = "OBSERVATION"
    QUESTION = "QUESTION"
    HYPOTHESIS = "HYPOTHESIS"
    SOURCE = "SOURCE"


class EdgeType(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    DERIVED_FROM = "DERIVED_FROM"
    RELATES_TO = "RELATES_TO"
    REQUIRES_VERIFICATION = "REQUIRES_VERIFICATION"
    ANSWERS = "ANSWERS"
    REFERENCES = "REFERENCES"


class EvidenceVerificationStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    CONTRADICTED = "CONTRADICTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    REJECTED = "REJECTED"


class IntegrityStatus(str, Enum):
    CONSISTENT = "CONSISTENT"
    INCONCLUSIVE = "INCONCLUSIVE"
    SUSPICIOUS = "SUSPICIOUS"
    TAMPERING_INDICATED = "TAMPERING_INDICATED"


class EvidenceOrigin(str, Enum):
    VERIFIED_EXTERNAL = "VERIFIED_EXTERNAL"
    USER_SUBMITTED = "USER_SUBMITTED"
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
    MODEL_INFERENCE = "MODEL_INFERENCE"
    UNVERIFIED = "UNVERIFIED"


class ActionType(str, Enum):
    CARRIER_TRACKING_LOOKUP = "CARRIER_TRACKING_LOOKUP"
    REQUEST_MERCHANT_FULFILLMENT = "REQUEST_MERCHANT_FULFILLMENT"
    REQUEST_BUYER_CLARIFICATION = "REQUEST_BUYER_CLARIFICATION"
    REQUEST_IMAGE_VERIFICATION = "REQUEST_IMAGE_VERIFICATION"
    CROSS_REFERENCE_TRANSACTION = "CROSS_REFERENCE_TRANSACTION"
    INTERNAL_ERP_AUDIT = "INTERNAL_ERP_AUDIT"
    REQUEST_PROOF_OF_DELIVERY = "REQUEST_PROOF_OF_DELIVERY"
    CARRIER_STATUS_MONITOR = "CARRIER_STATUS_MONITOR"
    ESCALATE_HUMAN_REVIEW = "ESCALATE_HUMAN_REVIEW"


class GraphNode(BaseModel):
    id: str
    type: NodeType
    label: str
    content: Dict[str, Any] = Field(default_factory=dict)
    source: str
    origin: EvidenceOrigin = EvidenceOrigin.UNVERIFIED
    verification_status: EvidenceVerificationStatus = EvidenceVerificationStatus.UNVERIFIED
    created_at: str
    verified_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source_id: str
    target_id: str
    type: EdgeType
    provenance: str
    weight: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvidenceGraphData(BaseModel):
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)


class CandidateAction(BaseModel):
    action_id: str
    action_type: ActionType
    title: str
    description: str
    target_party: str  # "BUYER", "MERCHANT", "CARRIER", "SYSTEM"
    expected_information_gain: float
    acquisition_friction: float
    utility_score: float
    rationale: str
    required_inputs: List[str] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    chosen_action: Optional[CandidateAction] = None
    all_candidates: List[CandidateAction] = Field(default_factory=list)
    policy_name: str
    selection_rationale: str
    timestamp: str


class DecisionReadinessEvaluation(BaseModel):
    is_decision_ready: bool
    requires_escalation: bool
    category: DisputeCategory
    satisfied_requirements: List[str] = Field(default_factory=list)
    missing_requirements: List[str] = Field(default_factory=list)
    active_contradictions: List[str] = Field(default_factory=list)
    recommended_state: InvestigationState
    rationale: str


class EvidenceIntegrityFinding(BaseModel):
    file_id: str
    file_name: str
    sha256_hash: str
    mime_type: str
    file_size_bytes: int
    integrity_status: IntegrityStatus
    exif_extracted: Dict[str, Any] = Field(default_factory=dict)
    has_gps: bool = False
    software_altered: bool = False
    findings_summary: str
    probabilistic_uncertainty_note: str


class EvidenceSubmissionRequest(BaseModel):
    action_id: Optional[str] = None
    submitter_role: str  # "MERCHANT" | "BUYER"
    notes: Optional[str] = None
    tracking_number: Optional[str] = None
    carrier_name: Optional[str] = None
    answers: Dict[str, Any] = Field(default_factory=dict)
    file_data_base64: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    verify_carrier_now: bool = False


class EvidenceSubmissionResult(BaseModel):
    success: bool
    evidence_id: str
    nodes_created: List[str]
    edges_created: List[str]
    previous_state: InvestigationState
    new_state: InvestigationState
    readiness: DecisionReadinessEvaluation
    integrity_finding: Optional[EvidenceIntegrityFinding] = None
    message: str


class DisputeSummary(BaseModel):
    dispute_id: str
    category: DisputeCategory
    state: InvestigationState
    data_source: DataSourceType
    amount: float
    currency: str
    buyer_id: str
    seller_id: str
    created_at: str
    updated_at: str
    open_questions_count: int
    is_decision_ready: bool
    item_name: Optional[str] = None
    buyer_name: Optional[str] = None


class DisputeDetail(BaseModel):
    dispute_id: str
    category: DisputeCategory
    state: InvestigationState
    data_source: DataSourceType
    amount: float
    currency: str
    buyer_id: str
    seller_id: str
    transaction_id: str
    created_at: str
    updated_at: str
    buyer_claim: str
    seller_response: Optional[str] = None
    evidence_graph: EvidenceGraphData
    current_policy_decision: Optional[PolicyDecision] = None
    readiness: DecisionReadinessEvaluation
    timeline: List[Dict[str, Any]] = Field(default_factory=list)
    integrity_findings: List[EvidenceIntegrityFinding] = Field(default_factory=list)
    item_name: Optional[str] = None
    buyer_name: Optional[str] = None


class InvestigationReport(BaseModel):
    report_id: str
    generated_at: str
    dispute_id: str
    category: DisputeCategory
    final_state: InvestigationState
    data_source: DataSourceType
    executive_summary: str
    verified_facts: List[str]
    unresolved_questions: List[str]
    identified_contradictions: List[str]
    missing_evidence_inventory: List[str]
    evidence_provenance_trail: List[Dict[str, Any]]
    integrity_findings: List[EvidenceIntegrityFinding]
    readiness_evaluation: DecisionReadinessEvaluation
    recommended_adjudication_handoff: str
    disclaimer: str = (
        "This investigation package was prepared automatically by the PayPal AI Dispute Investigator. "
        "The AI does NOT decide dispute outcomes or move funds. "
        "Every material finding is linked to verifiable evidence for human or PayPal adjudication review."
    )
