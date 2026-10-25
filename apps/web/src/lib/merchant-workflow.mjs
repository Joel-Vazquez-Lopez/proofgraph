// UI action routing based only on fields already provided in DisputeDetail.
export function merchantNextStep({ isReady, isReview, category, hasTracking, hasDeliveryRecord }) {
  if (isReady) return "review";
  if (isReview) return "human-review";
  if (category === "ITEM_NOT_RECEIVED") {
    if (!hasTracking) return "submit-tracking";
    if (!hasDeliveryRecord) return "carrier-lookup";
  }
  if (category === "SIGNIFICANTLY_NOT_AS_DESCRIBED") return "upload-condition";
  return "manual-follow-up";
}

export function hasUsableDeliveryObservation(shipment, nodes) {
  if (!shipment?.content?.tracking_number || !Array.isArray(nodes)) return false;
  return nodes.some((node) =>
    node?.type === "OBSERVATION" &&
    node?.content?.tracking_number === shipment.content.tracking_number &&
    node?.content?.status === "DELIVERED" &&
    node?.verification_status === "VERIFIED"
  );
}
