import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set, Tuple
import networkx as nx

from packages.shared_schemas.models import (
    NodeType,
    EdgeType,
    EvidenceOrigin,
    EvidenceVerificationStatus,
    GraphNode,
    GraphEdge,
    EvidenceGraphData,
)


class EvidenceGraph:
    """
    Typed, directed evidence graph backed by NetworkX.
    Maintains rigorous provenance, supports contradiction isolation,
    and facilitates active evidence gap analysis.
    """

    def __init__(self, dispute_id: str):
        self.dispute_id = dispute_id
        self._nx_graph = nx.DiGraph()
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: Dict[str, GraphEdge] = {}

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def add_node(
        self,
        node_type: NodeType,
        label: str,
        content: Dict[str, Any],
        source: str,
        node_id: Optional[str] = None,
        origin: EvidenceOrigin = EvidenceOrigin.UNVERIFIED,
        verification_status: EvidenceVerificationStatus = EvidenceVerificationStatus.UNVERIFIED,
        verified_at: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GraphNode:
        if not node_id:
            node_id = f"{node_type.value.lower()}_{uuid.uuid4().hex[:8]}"

        node = GraphNode(
            id=node_id,
            type=node_type,
            label=label,
            content=content,
            source=source,
            origin=origin,
            verification_status=verification_status,
            created_at=datetime.now(timezone.utc).isoformat(),
            verified_at=verified_at,
            metadata=metadata or {},
        )

        self._nodes[node_id] = node
        self._nx_graph.add_node(
            node_id,
            type=node_type.value,
            label=label,
            status=verification_status.value,
            origin=origin.value,
            source=source,
        )
        return node

    def verify_node(
        self,
        node_id: str,
        verifier_source: str,
        origin: Optional[EvidenceOrigin] = None,
        audit_note: str = ""
    ) -> GraphNode:
        if node_id not in self._nodes:
            raise KeyError(f"Node {node_id} not found in graph.")
        node = self._nodes[node_id]
        node.verification_status = EvidenceVerificationStatus.VERIFIED
        node.verified_at = datetime.now(timezone.utc).isoformat()
        if origin:
            node.origin = origin
            self._nx_graph.nodes[node_id]["origin"] = origin.value
        self._nx_graph.nodes[node_id]["status"] = EvidenceVerificationStatus.VERIFIED.value
        
        # Add explicit audit trail to metadata
        audit = node.metadata.setdefault("verification_audit", [])
        audit.append({
            "timestamp": node.verified_at,
            "verifier_source": verifier_source,
            "origin": node.origin.value,
            "note": audit_note or f"Independently verified by {verifier_source}"
        })
        return node

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType,
        provenance: str,
        edge_id: Optional[str] = None,
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GraphEdge:
        if source_id not in self._nodes:
            raise KeyError(f"Source node {source_id} does not exist in evidence graph.")
        if target_id not in self._nodes:
            raise KeyError(f"Target node {target_id} does not exist in evidence graph.")

        if not edge_id:
            edge_id = f"edge_{source_id}_{edge_type.value.lower()}_{target_id}"

        edge = GraphEdge(
            id=edge_id,
            source_id=source_id,
            target_id=target_id,
            type=edge_type,
            provenance=provenance,
            weight=weight,
            metadata=metadata or {},
        )

        self._edges[edge_id] = edge
        self._nx_graph.add_edge(
            source_id,
            target_id,
            id=edge_id,
            type=edge_type.value,
            weight=weight,
            provenance=provenance,
        )
        return edge

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self._nodes.get(node_id)

    def get_nodes_by_type(self, node_type: NodeType) -> List[GraphNode]:
        return [node for node in self._nodes.values() if node.type == node_type]

    def update_node_status(self, node_id: str, status: EvidenceVerificationStatus) -> None:
        if node_id in self._nodes:
            self._nodes[node_id].verification_status = status
            self._nx_graph.nodes[node_id]["status"] = status.value

    def get_contradictions(self) -> List[Tuple[GraphNode, GraphNode, GraphEdge]]:
        contradictions = []
        for edge in self._edges.values():
            if edge.type == EdgeType.CONTRADICTS:
                src = self._nodes.get(edge.source_id)
                tgt = self._nodes.get(edge.target_id)
                if src and tgt:
                    contradictions.append((src, tgt, edge))
        return contradictions

    def get_open_questions(self) -> List[GraphNode]:
        questions = self.get_nodes_by_type(NodeType.QUESTION)
        open_q = []
        for q in questions:
            # Check if any incoming edge is of type ANSWERS
            in_edges = [
                e for e in self._edges.values()
                if e.target_id == q.id and e.type == EdgeType.ANSWERS
            ]
            if not in_edges:
                open_q.append(q)
        return open_q

    def get_unverified_claims(self) -> List[GraphNode]:
        claims = self.get_nodes_by_type(NodeType.CLAIM)
        unverified = []
        for claim in claims:
            # Look for incoming SUPPORTS edges
            supporting_edges = [
                e for e in self._edges.values()
                if e.target_id == claim.id and e.type == EdgeType.SUPPORTS
            ]
            if not supporting_edges:
                unverified.append(claim)
        return unverified

    def to_data(self) -> EvidenceGraphData:
        return EvidenceGraphData(
            nodes=list(self._nodes.values()),
            edges=list(self._edges.values()),
        )

    @classmethod
    def from_data(cls, dispute_id: str, data: Any) -> "EvidenceGraph":
        if isinstance(data, dict):
            data = EvidenceGraphData(**data)
        graph = cls(dispute_id=dispute_id)
        for node in data.nodes:
            graph._nodes[node.id] = node
            graph._nx_graph.add_node(
                node.id,
                type=node.type.value,
                label=node.label,
                status=node.verification_status.value,
                source=node.source,
            )
        for edge in data.edges:
            graph._edges[edge.id] = edge
            graph._nx_graph.add_edge(
                edge.source_id,
                edge.target_id,
                id=edge.id,
                type=edge.type.value,
                weight=edge.weight,
                provenance=edge.provenance,
            )
        return graph
