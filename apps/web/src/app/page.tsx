"use client";

import React, { useState, useEffect, useCallback } from "react";
import { RefreshCw } from "lucide-react";

import { Header } from "@/components/Header";
import { CaseList, DisputeSummaryData } from "@/components/CaseList";
import { CaseOverview } from "@/components/CaseOverview";
import { ReviewPackageModal } from "@/components/ReviewPackageModal";
import { AdvancedWorkspace } from "@/components/AdvancedWorkspace";
import { GraphNodeData } from "@/components/EvidenceGraphView";

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
  if (orderNode?.content?.item_description) return orderNode.content.item_description;

  // Static fallback fixtures (never used if API returns item_name)
  const staticMap: Record<string, string> = {
    "PP-D-INR-8841": "Keychron Q1 Pro Wireless Mechanical Keyboard",
    "PP-D-INR-9923": "Sony WH-1000XM5 Noise Canceling Headphones",
    "PP-D-SNAD-3012": "1972 Vintage Chronograph Watch",
    "PP-D-DUP-4044": "Pro Cloud Hosting (Annual Subscription)",
  };
  if (dispute?.dispute_id) return staticMap[dispute.dispute_id] || "Purchased Item";
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
  const [selectedId, setSelectedId] = useState<string>("PP-D-INR-8841");
  const [dispute, setDispute] = useState<DisputeDetail | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(true);

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
    setLoadingList(true);
    try {
      const res = await fetch("/api/v1/disputes");
      if (res.ok) {
        const data = await res.json();
        setDisputes(data);
      }
    } catch (err) {
      console.error("Failed to load disputes:", err);
    } finally {
      setLoadingList(false);
    }
  }, []);

  const fetchDisputeDetail = useCallback(async (id: string) => {
    setLoadingDetail(true);
    setFeedback(null);
    setSelectedNode(null);
    setShowReviewModal(false);
    try {
      const res = await fetch(`/api/v1/disputes/${id}`);
      if (res.ok) {
        const data = await res.json();
        setDispute(data);
      }
    } catch (err) {
      console.error("Failed to load dispute detail:", err);
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  const refreshAll = useCallback(async () => {
    await fetchDisputes();
    if (selectedId) await fetchDisputeDetail(selectedId);
  }, [fetchDisputes, fetchDisputeDetail, selectedId]);

  useEffect(() => {
    fetchDisputes();
  }, [fetchDisputes]);

  useEffect(() => {
    if (selectedId) fetchDisputeDetail(selectedId);
  }, [selectedId, fetchDisputeDetail]);

  // ─────────────────────────────────────────────
  // Action Handlers
  // ─────────────────────────────────────────────

  const handleVerifyCarrier = async () => {
    if (!dispute) return;
    setCarrierVerifying(true);
    setFeedback(null);
    try {
      const res = await fetch(`/api/v1/disputes/${dispute.dispute_id}/verify-carrier`, {
        method: "POST",
      });
      if (res.ok) {
        const result = await res.json();
        setFeedback({
          type: "success",
          message: `Delivery record found. The case has moved to: ${result.new_state}. Note: this uses demonstration data, not a live carrier check.`,
        });
        await fetchDisputeDetail(dispute.dispute_id);
        await fetchDisputes();
      } else {
        const err = await res.json();
        setFeedback({
          type: "error",
          message: err.detail || "Carrier verification could not be completed.",
        });
      }
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    } finally {
      setCarrierVerifying(false);
    }
  };

  const handleSubmitTracking = async (carrierName: string, trackingNumber: string, notes: string) => {
    if (!dispute) return;
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
      const res = await fetch(`/api/v1/disputes/${dispute.dispute_id}/evidence`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const result = await res.json();
        setFeedback({
          type: "success",
          message: `Tracking submitted. Carrier verification status must be checked in the case evidence. Case state: ${result.new_state}.`,
        });
        await fetchDisputeDetail(dispute.dispute_id);
        await fetchDisputes();
      } else {
        const err = await res.json();
        setFeedback({ type: "error", message: err.detail || "Submission failed." });
      }
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    } finally {
      setSubmitting(false);
    }
  };

  const handleUploadFile = async (file: File) => {
    if (!dispute) return;
    setUploading(true);
    setFeedback(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("submitter_role", "MERCHANT");
      formData.append("notes", "Uploaded physical proof of delivery or condition document");
      const res = await fetch(`/api/v1/disputes/${dispute.dispute_id}/upload-evidence`, {
        method: "POST",
        body: formData,
      });
      if (res.ok) {
        const result = await res.json();
        setFeedback({
          type: "success",
          message: `Document uploaded and added to case. Authenticity has not been independently verified. Case state: ${result.new_state}.`,
        });
        await fetchDisputeDetail(dispute.dispute_id);
        await fetchDisputes();
      } else {
        const err = await res.json();
        setFeedback({ type: "error", message: err.detail || "File upload rejected." });
      }
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    } finally {
      setUploading(false);
    }
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
          <section className="lg:col-span-4 sticky top-[72px]">
            {loadingList ? (
              <div className="bg-white rounded-2xl border border-slate-200 p-8 flex flex-col items-center gap-3 text-slate-500">
                <RefreshCw className="w-6 h-6 animate-spin text-blue-600" />
                <span className="text-xs font-semibold">Loading cases…</span>
              </div>
            ) : (
              <CaseList
                disputes={disputes}
                selectedId={selectedId}
                onSelectCase={(id) => {
                  setSelectedId(id);
                  setShowAdvanced(false);
                }}
              />
            )}
          </section>

          {/* ── Right Column: Investigation View (8 cols) ── */}
          <section className="lg:col-span-8 flex flex-col gap-5">
            {loadingDetail ? (
              <div className="bg-white rounded-2xl border border-slate-200 p-12 flex flex-col items-center gap-3 text-slate-500">
                <RefreshCw className="w-6 h-6 animate-spin text-blue-600" />
                <span className="text-xs font-semibold">Loading case details…</span>
              </div>
            ) : dispute ? (
              <>
                {/* Primary investigation flow: What happened / What we know / What to do */}
                <CaseOverview
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
                <span className="text-sm font-semibold">Select a case from the list to begin investigation.</span>
              </div>
            )}
          </section>
        </div>
      </main>

      {/* ── Review Package Modal (overlaid, not inline) ── */}
      {dispute && (
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
