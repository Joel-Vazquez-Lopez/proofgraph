// Evidence display rules shared by the review modal and downloaded report.
// Never infer independent verification from evaluator readiness or a synthetic fixture.
export const HUMAN_REVIEW_NOTICE =
  "ProofGraph organizes evidence for review; it does not determine dispute outcomes or move funds.";

const clean = (value) => typeof value === "string" ? value.trim() : "";

export function humanizeRequirement(value) {
  return clean(value).replace(/_/g, " ").toLowerCase();
}

export function evidenceProvenance(node) {
  if (node?.origin === "SYNTHETIC_FIXTURE") {
    return { label: "Simulated record", description: "Demonstration data; not independently verified", externallyVerified: false };
  }
  if (node?.origin === "USER_SUBMITTED") {
    return { label: "User submitted", description: "Source supplied this record; authenticity is not independently established", externallyVerified: false };
  }
  if (node?.origin === "MODEL_INFERENCE") {
    return { label: "Model inference", description: "An interpretation, not a verified observation", externallyVerified: false };
  }
  if (node?.origin === "VERIFIED_EXTERNAL" && node?.verification_status === "VERIFIED") {
    return { label: "Externally verified", description: "The API identifies this as independently verified evidence", externallyVerified: true };
  }
  return {
    label: "Unverified source",
    description: "Independent verification is not established by the available fields",
    externallyVerified: false,
  };
}

export function evidenceEntries(dispute) {
  const nodes = Array.isArray(dispute?.evidence_graph?.nodes) ? dispute.evidence_graph.nodes : [];
  const types = new Set(["TRANSACTION", "ORDER", "SHIPMENT", "OBSERVATION", "EVIDENCE_ITEM", "PRODUCT"]);
  return nodes.filter((node) => types.has(node?.type)).map((node) => ({
    id: clean(node.id) || clean(node.label),
    title: clean(node.label) || clean(node.type) || "Evidence record",
    source: clean(node.source) || "Source not specified",
    status: clean(node.verification_status) || "UNVERIFIED",
    ...evidenceProvenance(node),
  }));
}

export function investigationSummary(dispute) {
  const readiness = dispute?.readiness || {};
  return {
    isReady: readiness.is_decision_ready === true,
    requirements: Array.isArray(readiness.satisfied_requirements) ? readiness.satisfied_requirements : [],
    missing: Array.isArray(readiness.missing_requirements) ? readiness.missing_requirements : [],
    contradictions: Array.isArray(readiness.active_contradictions) ? readiness.active_contradictions : [],
    evidence: evidenceEntries(dispute),
  };
}

export function generateReviewMarkdown(dispute, productName, buyerName, generatedAt = new Date().toISOString()) {
  const view = investigationSummary(dispute);
  const lines = [
    "# ProofGraph dispute investigation summary",
    `**Case ID:** ${dispute?.dispute_id || "Unknown"}`,
    `**Transaction ID:** ${dispute?.transaction_id || "Not available"}`,
    `**Product:** ${productName || "Not specified"}`,
    `**Amount:** ${dispute?.amount ?? "Not available"} ${dispute?.currency || ""}`,
    `**Buyer:** ${buyerName || "Not specified"}`,
    `**Status:** ${view.isReady ? "Ready for human review" : "Investigation in progress"}`,
    `**Generated:** ${generatedAt}`,
    "",
    "## Statements (claims, not independently established facts)",
    `- Buyer: ${dispute?.buyer_claim || "No statement on record"}`,
    `- Merchant: ${dispute?.seller_response || "No statement on record"}`,
    "",
    "## Evidence on file (with provenance)",
  ];
  if (!view.evidence.length) lines.push("- No evidence items available.");
  for (const record of view.evidence) {
    lines.push(`- ${record.title} — ${record.label}; ${record.description}; source: ${record.source}; API status: ${record.status}`);
  }
  lines.push("", "## Requirements met (evaluator assessment, not proof of independent verification)");
  if (!view.requirements.length) lines.push("- None listed.");
  else for (const requirement of view.requirements) lines.push(`- ${humanizeRequirement(requirement)}`);
  lines.push("", "## Unresolved requirements");
  if (!view.missing.length) lines.push("- None listed by the evaluator.");
  else for (const item of view.missing) lines.push(`- ${humanizeRequirement(item)}`);
  lines.push("", "## Contradictions requiring review");
  if (!view.contradictions.length) lines.push("- None identified by the evaluator; this does not establish that the evidence is accurate.");
  else for (const conflict of view.contradictions) lines.push(`- ${conflict}`);
  lines.push(
    "", "## Current assessment",
    `- Recommended state: ${dispute?.readiness?.recommended_state || dispute?.state || "Not available"}`,
    `- Rationale: ${dispute?.readiness?.rationale || "No rationale supplied"}`,
    "", `> ${HUMAN_REVIEW_NOTICE}`
  );
  return lines.join("\n") + "\n";
}
