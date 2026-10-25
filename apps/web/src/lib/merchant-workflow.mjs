// UI action routing based only on fields already provided in DisputeDetail.
export function merchantNextStep({ isReady, isReview, category, hasTracking, hasDeliveryRecord, hasConditionEvidence = false }) {
  if (isReady) return "review";
  if (isReview) return "human-review";
  if (category === "ITEM_NOT_RECEIVED") {
    if (!hasTracking) return "submit-tracking";
    if (!hasDeliveryRecord) return "carrier-lookup";
  }
  if (category === "SIGNIFICANTLY_NOT_AS_DESCRIBED") return hasConditionEvidence ? "condition-submitted" : "upload-condition";
  return "manual-follow-up";
}

export function hasUsableDeliveryObservation(shipment, nodes) {
  if (!shipment?.content?.tracking_number || !Array.isArray(nodes)) return false;
  const latest = latestCarrierObservation(shipment, nodes);
  return latest?.content?.status === "DELIVERED" &&
    latest?.verification_status === "VERIFIED";
}

// Backend carrier checks append immutable observations. Read the latest event for
// the selected tracking number; a historical delivery scan must not eclipse a
// subsequent NOT_FOUND, EXCEPTION, or corrected observation.
export function latestCarrierObservation(shipment, nodes) {
  const tracking = shipment?.content?.tracking_number;
  if (!tracking || !Array.isArray(nodes)) return null;
  return nodes.filter((node) =>
    node?.type === "OBSERVATION" &&
    node?.content?.tracking_number === tracking &&
    typeof node?.content?.status === "string"
  ).at(-1) || null;
}
