"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { RefreshCw } from "lucide-react";

import { Header } from "@/components/Header";
import { CaseList, DisputeSummaryData } from "@/components/CaseList";
import { CaseOverview } from "@/components/CaseOverview";
import { ReviewPackageModal } from "@/components/ReviewPackageModal";
import { AdvancedWorkspace } from "@/components/AdvancedWorkspace";
import { GraphNodeData } from "@/components/EvidenceGraphView";
import { getResponseError, isCurrentCase, submissionMessage } from "@/lib/investigation-actions.mjs";

// ─────────────────────────────────────────────
// Types aligned with the backend API contracts
// ─────────────────────────────────────────────

interface DisputeDetail extends DisputeSummaryData {
  transaction_id: string;
  buyer_claim: string;
  seller_response?: string;
  evidence_graph: {
    nodes: any[];
    edges: any[];
  };
  current_policy_decision?: {
    chosen_action?: {
      action_id: string;
      action_type: string;
      title: string;
      description: string;
      target_party: string;
      expected_information_gain: number;
      acquisition_friction: number;
      utility_score: number;
      rationale: string;
    };
    selection_rationale: string;
  };
  readiness: {
    is_decision_ready: boolean;
    requires_escalation: boolean;
    satisfied_requirements: string[];
    missing_requirements: string[];
    active_contradictions: string[];
    recommended_state: string;
    rationale: string;
  };
  timeline: Array<{
    timestamp: string;
    actor: string;
    action: string;
    state_transition: string;
    notes?: string;
  }>;
  integrity_findings: any[];
}

// ─────────────────────────────────────────────
// Helpers: derive human-friendly product name from API response
// ─────────────────────────────────────────────

function resolveProductName(dispute: DisputeDetail | null, summary: DisputeSummaryData | undefined): string {
  if (dispute?.item_name) return dispute.item_name;
  if (summary?.item_name) return summary.item_name;

  // Fallback from evidence graph ORDER node
  const orderNode = dispute?.evidence_graph?.nodes?.find((n: any) => n.type === "ORDER");
  if (orderNode?.content?.item_name) return orderNode.content.item_name;
  if (orderNode?.content?.item_description) return orderNode.content.item_description;
  return "Purchased Item";
}

function resolveBuyerName(dispute: DisputeDetail | null, summary: DisputeSummaryData | undefined): string {
  if (dispute?.buyer_name) return dispute.buyer_name;
  if (summary?.buyer_name) return summary.buyer_name;
  const rawId = dispute?.buyer_id || "";
  return rawId.replace(/^payer_/, "").replace(/_\d+$/, "").replace(/_/g, " ")
    .split(" ").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ") || rawId;
}

// ─────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────

export default function ProofGraphPage() {
  // ── Core Data State ───────────────────────────
  const [disputes, setDisputes] = useState<DisputeSummaryData[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [dispute, setDispute] = useState<DisputeDetail | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const activeCaseRef = useRef("");
  const detailRequestRef = useRef(0);
  const listRequestRef = useRef(0);
  const detailAbortRef = useRef<AbortController | null>(null);

  // ── UI State ─────────────────────────────────
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showReviewModal, setShowReviewModal] = useState(false);
  const [selectedNode, setSelectedNode] = useState<GraphNodeData | null>(null);

  // ── Action Loading State ──────────────────────
  const [submitting, setSubmitting] = useState(false);
  const [carrierVerifying, setCarrierVerifying] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error" | "info"; message: string } | null>(null);

  // ─────────────────────────────────────────────
  // Data Fetching
  // ─────────────────────────────────────────────

  const fetchDisputes = useCallback(async () => {
    const request = ++listRequestRef.current;
    setLoadingList(true);
    setListError(null);
    try {
      const res = await fetch("/api/v1/disputes");
      if (!res.ok) throw new Error(await getResponseError(res, "Could not load cases"));
      const data: DisputeSummaryData[] = await res.json();
      if (request !== listRequestRef.current) return;
      setDisputes(data);
      if (!data.some((item) => item.dispute_id === activeCaseRef.current)) {
        const nextId = data[0]?.dispute_id || "";
        activeCaseRef.current = nextId;
        setSelectedId(nextId);
        setDispute(null);
        setFeedback(null);
      }
    } catch (err: any) {
      if (request === listRequestRef.current) {
        setListError(err?.message || "Could not load cases.");
      }
    } finally {
      if (request === listRequestRef.current) setLoadingList(false);
    }
  }, []);

  const fetchDisputeDetail = useCallback(async (id: string) => {
    if (!id || activeCaseRef.current !== id) return;
    const request = ++detailRequestRef.current;
    detailAbortRef.current?.abort();
    const controller = new AbortController();
    detailAbortRef.current = controller;
    setLoadingDetail(true);
    setDetailError(null);
    setDispute(null); // Never display an old case while fetching another.
    setSelectedNode(null);
    setShowReviewModal(false);
    try {
      const res = await fetch(`/api/v1/disputes/${encodeURIComponent(id)}`, { signal: controller.signal });
      if (!res.ok) throw new Error(await getResponseError(res, "Could not load case details"));
      const data: DisputeDetail = await res.json();
      if (isCurrentCase(id, activeCaseRef.current, request, detailRequestRef.current)) {
        setDispute(data);
      }
    } catch (err: any) {
      if (!controller.signal.aborted && isCurrentCase(id, activeCaseRef.current, request, detailRequestRef.current)) {
        setDetailError(err?.message || "Could not load this investigation.");
      }
    } finally {
      if (isCurrentCase(id, activeCaseRef.current, request, detailRequestRef.current)) {
        setLoadingDetail(false);
      }
    }
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([fetchDisputes(), activeCaseRef.current ? fetchDisputeDetail(activeCaseRef.current) : Promise.resolve()]);
  }, [fetchDisputes, fetchDisputeDetail]);

  useEffect(() => { fetchDisputes(); }, [fetchDisputes]);
  useEffect(() => {
    if (selectedId) fetchDisputeDetail(selectedId);
    else { detailAbortRef.current?.abort(); setDispute(null); setLoadingDetail(false); }
    return () => detailAbortRef.current?.abort();
  }, [selectedId, fetchDisputeDetail]);

  const selectCase = (id: string) => {
    if (id === activeCaseRef.current) return;
    activeCaseRef.current = id;
    detailAbortRef.current?.abort();
    ++detailRequestRef.current;
    setSelectedId(id);
    setDispute(null);
    setDetailError(null);
    setFeedback(null);
    setShowAdvanced(false);
    setShowReviewModal(false);
  };

  const reportActionFeedback = (id: string, type: "success" | "error", message: string) => {
    if (activeCaseRef.current === id) setFeedback({ type, message });
  };

  // ─────────────────────────────────────────────
  // Action Handlers
  // ─────────────────────────────────────────────

  const handleVerifyCarrier = async () => {
    if (!dispute || carrierVerifying) return;
    const id = dispute.dispute_id;
    setCarrierVerifying(true);
    setFeedback(null);
    try {
      const res = await fetch(`/api/v1/disputes/${encodeURIComponent(id)}/verify-carrier`, { method: "POST" });
      if (!res.ok) throw new Error(await getResponseError(res, "Carrier lookup failed"));
      const result = await res.json();
      reportActionFeedback(id, "success", submissionMessage("carrier", result, dispute.data_source === "SYNTHETIC_FIXTURE"));
      await fetchDisputeDetail(id);
      await fetchDisputes();
    } catch (err: any) {
      reportActionFeedback(id, "error", err?.message || "Carrier lookup failed.");
    } finally { setCarrierVerifying(false); }
  };

  const handleSubmitTracking = async (carrierName: string, trackingNumber: string, notes: string) => {
    if (!dispute || submitting) return;
    const id = dispute.dispute_id;
    setSubmitting(true);
    setFeedback(null);
    try {
      const payload = {
        action_id: dispute.current_policy_decision?.chosen_action?.action_id || "act_merchant_tracking",
        submitter_role: "MERCHANT",
        carrier_name: carrierName,
        tracking_number: trackingNumber,
        verify_carrier_now: true,
        notes,
      };
      const res = await fetch(`/api/v1/disputes/${encodeURIComponent(id)}/evidence`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await getResponseError(res, "Tracking submission failed"));
      const result = await res.json();
      reportActionFeedback(id, "success", submissionMessage("tracking", result, dispute.data_source === "SYNTHETIC_FIXTURE"));
      await fetchDisputeDetail(id);
      await fetchDisputes();
    } catch (err: any) {
      reportActionFeedback(id, "error", err?.message || "Tracking submission failed.");
    } finally { setSubmitting(false); }
  };

  const handleUploadFile = async (file: File) => {
    if (!dispute || uploading) return;
    const id = dispute.dispute_id;
    setUploading(true);
    setFeedback(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("submitter_role", "MERCHANT");
      formData.append("notes", "Merchant-submitted supporting evidence");
      const res = await fetch(`/api/v1/disputes/${encodeURIComponent(id)}/upload-evidence`, { method: "POST", body: formData });
      if (!res.ok) throw new Error(await getResponseError(res, "File upload failed"));
      const result = await res.json();
      reportActionFeedback(id, "success", submissionMessage("upload", result, dispute.data_source === "SYNTHETIC_FIXTURE"));
      await fetchDisputeDetail(id);
      await fetchDisputes();
    } catch (err: any) {
      reportActionFeedback(id, "error", err?.message || "File upload failed.");
    } finally { setUploading(false); }
  };

  // ─────────────────────────────────────────────
  // Derived Display Values
  // ─────────────────────────────────────────────

  const selectedSummary = disputes.find((d) => d.dispute_id === selectedId);
  const productName = resolveProductName(dispute, selectedSummary);
  const buyerName = resolveBuyerName(dispute, selectedSummary);

  // ─────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-slate-100/70 text-slate-900 pb-24 font-sans antialiased">
      {/* ── Header ─────────────────────────────── */}
      <Header
        onRefresh={refreshAll}
        isRefreshing={loadingList || loadingDetail}
      />

      {/* ── Main Layout ────────────────────────── */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-6">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">

          {/* ── Left Column: Case List (4 cols) ── */}
          <section aria-label="Dispute cases" className="lg:col-span-4 lg:sticky lg:top-[72px]">
            {loadingList && disputes.length === 0 ? (
              <div className="bg-white rounded-2xl border border-slate-200 p-8 flex flex-col items-center gap-3 text-slate-500">
                <RefreshCw className="w-6 h-6 animate-spin text-blue-600" />
                <span className="text-xs font-semibold">Loading cases…</span>
              </div>
            ) : (
              <div className="space-y-3">
                {listError && (
                  <div role="alert" className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-900">
                    <p>{listError}</p>
                    <button type="button" onClick={fetchDisputes} className="mt-2 font-bold underline focus-visible:ring-2 focus-visible:ring-rose-600">Retry loading cases</button>
                  </div>
                )}
                <CaseList disputes={disputes} selectedId={selectedId} onSelectCase={selectCase} />
              </div>
            )}
          </section>

          {/* ── Right Column: Investigation View (8 cols) ── */}
          <section className="lg:col-span-8 flex flex-col gap-5">
            {loadingDetail ? (
              <div className="bg-white rounded-2xl border border-slate-200 p-12 flex flex-col items-center gap-3 text-slate-500">
                <RefreshCw className="w-6 h-6 animate-spin text-blue-600" />
                <span className="text-xs font-semibold">Loading case details…</span>
              </div>
            ) : detailError ? (
              <div role="alert" className="bg-white rounded-2xl border border-rose-200 p-8 space-y-3 text-rose-900">
                <h2 className="font-bold text-sm">Could not load this investigation</h2>
                <p className="text-xs">{detailError}</p>
                {feedback && <p className="text-xs">{feedback.message}</p>}
                <button type="button" onClick={() => fetchDisputeDetail(selectedId)}
                  className="px-4 py-2 bg-slate-900 text-white rounded-lg text-xs font-semibold focus-visible:ring-2 focus-visible:ring-blue-600">Retry case details</button>
              </div>
            ) : dispute?.dispute_id === selectedId ? (
              <>
                {/* Primary investigation flow: What happened / What we know / What to do */}
                <CaseOverview
                  key={dispute.dispute_id}
                  dispute={dispute}
                  productName={productName}
                  buyerName={buyerName}
                  onVerifyCarrier={handleVerifyCarrier}
                  onSubmitTracking={handleSubmitTracking}
                  onUploadFile={handleUploadFile}
                  onOpenReviewModal={() => setShowReviewModal(true)}
                  carrierVerifying={carrierVerifying}
                  submitting={submitting}
                  uploading={uploading}
                  feedback={feedback}
                />

                {/* Progressive disclosure: Evidence Graph, Audit Timeline, Diagnostics */}
                <AdvancedWorkspace
                  dispute={dispute}
                  isOpen={showAdvanced}
                  onToggle={() => setShowAdvanced((prev) => !prev)}
                  selectedNode={selectedNode}
                  onSelectNode={setSelectedNode}
                />
              </>
            ) : (
              <div className="bg-white rounded-2xl border border-slate-200 p-12 flex flex-col items-center gap-3 text-slate-500">
                <span className="text-sm font-semibold">{selectedId ? "No case details available. Retry or select another case." : "Select a case to begin investigation."}</span>
              </div>
            )}
          </section>
        </div>
      </main>

      {/* ── Review Package Modal (overlaid, not inline) ── */}
      {dispute?.dispute_id === selectedId && (
        <ReviewPackageModal
          isOpen={showReviewModal}
          onClose={() => setShowReviewModal(false)}
          dispute={dispute}
          productName={productName}
          buyerName={buyerName}
        />
      )}
    </div>
  );
}
