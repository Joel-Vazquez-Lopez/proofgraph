export async function getResponseError(response, fallback) {
  let payload = null;
  try { payload = await response.json(); } catch { /* non-JSON responses are possible */ }
  const detail = payload?.detail;
  const message = typeof detail === "string"
    ? detail
    : Array.isArray(detail)
      ? detail.map((entry) => entry?.msg).filter(Boolean).join("; ")
      : "";
  return message || `${fallback} (HTTP ${response.status})`;
}

export function isCurrentCase(requestedCaseId, selectedCaseId, requestNumber, latestRequestNumber) {
  return Boolean(requestedCaseId) &&
    requestedCaseId === selectedCaseId &&
    requestNumber === latestRequestNumber;
}

export function submissionMessage(kind, result, synthetic) {
  const state = result?.new_state ? ` Case state: ${result.new_state}.` : "";
  if (kind === "upload") {
    return "Document received and added to the case. File checks do not establish authenticity or independent verification." + state;
  }
  if (kind === "tracking") {
    return "Tracking details submitted. Consult the updated evidence for delivery status; submitting a tracking number does not verify delivery." + state;
  }
  return (synthetic
    ? "Carrier lookup finished using simulated demonstration data, not a live carrier integration."
    : "Carrier lookup request completed. Consult the updated evidence to determine whether delivery was independently verified.") + state;
}

export function friendlyRequestError(error, fallback) {
  const message = typeof error?.message === "string" ? error.message : "";
  if (!message || /^(failed to fetch|load failed|networkerror|network request failed)/i.test(message)) {
    return `${fallback}. Check your connection, then retry.`;
  }
  return message;
}
