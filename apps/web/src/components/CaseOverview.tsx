"use client";

import React, { useState } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  Clock,
  ArrowRight,
  Truck,
  User,
  Upload,
  RefreshCw,
  AlertOctagon,
  ShieldCheck,
  Send,
  FileText,
  Building2,
  Sparkles,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

interface CaseOverviewProps {
  dispute: any;
  productName: string;
  buyerName: string;
  onVerifyCarrier: () => Promise<void>;
  onSubmitTracking: (carrierName: string, trackingNumber: string, notes: string) => Promise<void>;
  onUploadFile: (file: File) => Promise<void>;
  onOpenReviewModal: () => void;
  carrierVerifying: boolean;
  submitting: boolean;
  uploading: boolean;
  feedback: { type: "success" | "error" | "info"; message: string } | null;
}

export const CaseOverview: React.FC<CaseOverviewProps> = ({
  dispute,
  productName,
  buyerName,
  onVerifyCarrier,
  onSubmitTracking,
  onUploadFile,
  onOpenReviewModal,
  carrierVerifying,
  submitting,
  uploading,
  feedback,
}) => {
  const [carrier, setCarrier] = useState("USPS");
  const [trackingNumber, setTrackingNumber] = useState("940010009999");
  const [showOriginalStatements, setShowOriginalStatements] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [confirmCheck, setConfirmCheck] = useState(false);

  if (!dispute) return null;

  const isReady = dispute.readiness?.is_decision_ready || dispute.is_decision_ready;
  const isReview = dispute.state === "REVIEW_REQUIRED";
  const contradictions = dispute.readiness?.active_contradictions || [];
  const satisfiedReqs = dispute.readiness?.satisfied_requirements || [];
  const missingReqs = dispute.readiness?.missing_requirements || [];

  const nodes = dispute.evidence_graph?.nodes || [];
  const shipmentNode = nodes.find((n: any) => n.type === "SHIPMENT");
  const orderNode = nodes.find((n: any) => n.type === "ORDER");

  const hasTracking = !!shipmentNode;
  // Only mark as carrier-verified when the backend explicitly sets VERIFIED_EXTERNAL
  const isCarrierVerified = shipmentNode?.verification_status === "VERIFIED_EXTERNAL";

  const getHumanCategory = (cat: string) => {
    if (cat === "ITEM_NOT_RECEIVED") return "Item not received";
    if (cat === "SIGNIFICANTLY_NOT_AS_DESCRIBED") return "Item not as described";
    if (cat === "UNAUTHORIZED_TRANSACTION") return "Unauthorized transaction";
    if (cat === "DUPLICATE_CHARGE") return "Duplicate charge";
    return cat.replace(/_/g, " ").toLowerCase();
  };

  // Concise plain-English summary of what happened
  const getConciseSummary = () => {
    if (dispute.category === "ITEM_NOT_RECEIVED") {
      if (!hasTracking) {
        return "The customer says the order never arrived. The merchant reports it was shipped, but no tracking record has been provided yet. Delivery cannot be confirmed.";
      }
      if (!isCarrierVerified) {
        return "The customer says the order never arrived. A tracking number has been recorded, but delivery has not yet been checked with the carrier.";
      }
      if (contradictions.length > 0) {
        return "The customer says the order never arrived. A delivery record is available, but the destination address in that record does not match the order address. This needs review.";
      }
      return "The customer says the order never arrived. Payment and delivery records have been checked. The case is ready for a human to review and decide.";
    }
    if (dispute.category === "SIGNIFICANTLY_NOT_AS_DESCRIBED") {
      return "The customer says the item they received does not match the listing. We have payment and order records. A photo or condition document from the merchant would help clarify.";
    }
    if (dispute.category === "DUPLICATE_CHARGE") {
      return "The customer says they were charged twice for the same order. We are checking transaction records to see whether both charges settled.";
    }
    if (dispute.category === "UNAUTHORIZED_TRANSACTION") {
      return "The customer says they did not authorize this payment. Transaction records are on file. Human review is needed to evaluate account security.";
    }
    return "A dispute has been opened for this transaction. Records are being reviewed.";
  };

  const handleTrackingSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!trackingNumber.trim()) return;
    onSubmitTracking(carrier, trackingNumber, "Merchant-provided shipping details");
  };

  const handleFileUpload = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;
    onUploadFile(selectedFile);
  };

  return (
    <div className="space-y-5">
      {/* Feedback Banner */}
      {feedback && (
        <div
          className={`p-4 rounded-2xl border text-xs flex items-start gap-3 animate-in fade-in duration-200 ${
            feedback.type === "success"
              ? "bg-emerald-50 border-emerald-200 text-emerald-900"
              : feedback.type === "error"
              ? "bg-rose-50 border-rose-200 text-rose-900"
              : "bg-blue-50 border-blue-200 text-blue-900"
          }`}
        >
          {feedback.type === "success" ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
          ) : feedback.type === "error" ? (
            <AlertOctagon className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          ) : (
            <Sparkles className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
          )}
          <div className="flex-1 font-medium">{feedback.message}</div>
        </div>
      )}

      {/* SECTION 1: WHAT HAPPENED? */}
      <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-xs space-y-4">
        <div className="flex items-start justify-between gap-4 pb-3 border-b border-slate-100">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              What happened
            </span>
            <div className="flex items-center gap-2 mt-0.5">
              <h2 className="text-lg font-extrabold text-slate-900 tracking-tight leading-tight">
                {productName}
              </h2>
              <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200 shrink-0">
                {getHumanCategory(dispute.category)}
              </span>
            </div>
          </div>
          <div className="text-right shrink-0">
            <span className="text-xl font-black text-slate-900">
              ${dispute.amount.toFixed(2)}{" "}
              <span className="text-xs font-semibold text-slate-400">{dispute.currency}</span>
            </span>
            <p className="text-[10px] font-mono text-slate-400 mt-0.5">
              Case {dispute.dispute_id}
            </p>
          </div>
        </div>

        {/* Concise plain-English summary */}
        <p className="text-sm text-slate-700 leading-relaxed">
          {getConciseSummary()}
        </p>

        {/* View original statements (progressive disclosure) */}
        <div>
          <button
            onClick={() => setShowOriginalStatements((v) => !v)}
            className="flex items-center gap-1.5 text-xs text-blue-700 font-semibold hover:text-blue-900 transition-colors"
          >
            {showOriginalStatements ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
            <span>{showOriginalStatements ? "Hide original statements" : "View original statements"}</span>
          </button>

          {showOriginalStatements && (
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 animate-in slide-in-from-top-1 duration-150">
              <div className="bg-slate-50 rounded-xl p-3.5 border border-slate-200/80">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-5 h-5 rounded-full bg-blue-100 flex items-center justify-center">
                    <User className="w-3 h-3 text-blue-700" />
                  </div>
                  <span className="text-xs font-bold text-slate-700">{buyerName} — Customer statement</span>
                </div>
                <p className="text-xs text-slate-700 italic leading-relaxed">
                  "{dispute.buyer_claim || "Item did not arrive."}"
                </p>
                <p className="text-[10px] text-slate-400 mt-2">
                  Opened {new Date(dispute.created_at).toLocaleDateString()}
                </p>
              </div>

              <div className="bg-slate-50 rounded-xl p-3.5 border border-slate-200/80">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-5 h-5 rounded-full bg-slate-200 flex items-center justify-center">
                    <Building2 className="w-3 h-3 text-slate-600" />
                  </div>
                  <span className="text-xs font-bold text-slate-700">Merchant record</span>
                </div>
                <p className="text-xs text-slate-700 italic leading-relaxed">
                  "{dispute.seller_response || "Order was fulfilled and shipped."}"
                </p>
                <p className="text-[10px] text-slate-400 mt-2">
                  Order #{orderNode?.content?.order_id || dispute.transaction_id || "ORD-2026"}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* SECTION 2: WHAT DID WE FIND? */}
      <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-xs space-y-4">
        <div className="pb-2 border-b border-slate-100">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            What we found
          </span>
          <h3 className="text-sm font-bold text-slate-900 mt-0.5">
            What we know so far
          </h3>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Confirmed */}
          <div className="space-y-2">
            <h4 className="text-[11px] font-bold text-emerald-800 uppercase tracking-wider flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> On record
            </h4>
            <div className="space-y-2 text-xs">
              <div className="p-3 rounded-xl bg-emerald-50/60 border border-emerald-200/60 text-slate-800 flex items-start gap-2.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 mt-0.5 shrink-0" />
                <div>
                  <span className="font-semibold">Payment confirmed</span>
                  <p className="text-[11px] text-slate-600 mt-0.5">
                    ${dispute.amount.toFixed(2)} {dispute.currency} processed via PayPal for {productName}.
                    This is from PayPal's own transaction records.
                  </p>
                </div>
              </div>

              {orderNode?.content?.shipping_address && (
                <div className="p-3 rounded-xl bg-emerald-50/60 border border-emerald-200/60 text-slate-800 flex items-start gap-2.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 mt-0.5 shrink-0" />
                  <div>
                    <span className="font-semibold">Delivery destination on order</span>
                    <p className="text-[11px] text-slate-600 mt-0.5">
                      {orderNode.content.shipping_address.city},{" "}
                      {orderNode.content.shipping_address.state} — as recorded at checkout.
                    </p>
                  </div>
                </div>
              )}

              {hasTracking && (
                <div className="p-3 rounded-xl bg-emerald-50/60 border border-emerald-200/60 text-slate-800 flex items-start gap-2.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 mt-0.5 shrink-0" />
                  <div>
                    <span className="font-semibold">Tracking number recorded</span>
                    <p className="text-[11px] text-slate-600 mt-0.5">
                      {shipmentNode.content?.carrier_name} tracking{" "}
                      <span className="font-mono">{shipmentNode.content?.tracking_number}</span>{" "}
                      — provided by the merchant. Delivery status is{" "}
                      {isCarrierVerified ? "checked with the carrier (demonstration data)" : "not yet checked"}.
                    </p>
                  </div>
                </div>
              )}

              {isCarrierVerified && (
                <div className="p-3 rounded-xl bg-emerald-50/60 border border-emerald-200/60 text-slate-800 flex items-start gap-2.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 mt-0.5 shrink-0" />
                  <div>
                    <span className="font-semibold">Delivery record available</span>
                    <p className="text-[11px] text-slate-600 mt-0.5">
                      Delivery to {shipmentNode.content?.delivery_address?.city},{" "}
                      {shipmentNode.content?.delivery_address?.state} is shown in demonstration records.
                      This is synthetic data, not a live carrier check.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Unresolved */}
          <div className="space-y-2">
            <h4 className="text-[11px] font-bold text-amber-800 uppercase tracking-wider flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600" /> Not yet confirmed
            </h4>
            <div className="space-y-2 text-xs">
              {contradictions.length > 0 ? (
                <>
                  {contradictions.map((c: string, idx: number) => (
                    <div key={idx} className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-950 flex items-start gap-2.5">
                      <AlertOctagon className="w-3.5 h-3.5 text-rose-600 mt-0.5 shrink-0" />
                      <div>
                        <span className="font-semibold text-rose-900">These delivery details don't match</span>
                        <p className="text-[11px] text-rose-800/90 mt-0.5 leading-relaxed">
                          {c} — The delivery record is part of our demonstration data and has not been independently checked with the carrier.
                        </p>
                      </div>
                    </div>
                  ))}
                </>
              ) : !hasTracking ? (
                <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-950 flex items-start gap-2.5">
                  <Clock className="w-3.5 h-3.5 text-amber-600 mt-0.5 shrink-0" />
                  <div>
                    <span className="font-semibold">No tracking information yet</span>
                    <p className="text-[11px] text-amber-800/90 mt-0.5">
                      Delivery cannot be checked until a tracking number is provided.
                    </p>
                  </div>
                </div>
              ) : !isCarrierVerified ? (
                <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-950 flex items-start gap-2.5">
                  <Clock className="w-3.5 h-3.5 text-amber-600 mt-0.5 shrink-0" />
                  <div>
                    <span className="font-semibold">Delivery not yet checked</span>
                    <p className="text-[11px] text-amber-800/90 mt-0.5">
                      The tracking number is recorded, but we haven't checked the carrier yet to confirm delivery.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="p-3 rounded-xl bg-slate-50 border border-slate-100 text-slate-700 flex items-start gap-2.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 mt-0.5 shrink-0" />
                  <div>
                    <span className="font-semibold text-slate-900">No open questions</span>
                    <p className="text-[11px] text-slate-600 mt-0.5">
                      All required records are in. The case is ready for a human reviewer to decide.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* SECTION 3: WHAT SHOULD I DO NEXT? — one primary action */}
      <div className="rounded-2xl border p-5 bg-white border-slate-200 shadow-xs">
        <div className="mb-4">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            What to do next
          </span>
        </div>

        {/* READY */}
        {isReady ? (
          <div className="flex items-start gap-4">
            <div className="w-11 h-11 rounded-2xl bg-emerald-100 flex items-center justify-center shrink-0">
              <ShieldCheck className="w-5 h-5 text-emerald-700" />
            </div>
            <div className="flex-1 space-y-3">
              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  This case is ready for a human reviewer.
                </h3>
                <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                  Records have been gathered. A case summary is ready to share with the reviewer who will make the final decision.
                  ProofGraph does not decide dispute outcomes.
                </p>
              </div>
              <button
                onClick={onOpenReviewModal}
                className="px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold flex items-center gap-2 transition-all shadow-sm"
              >
                <FileText className="w-3.5 h-3.5" />
                <span>See case summary</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

        /* CONTRADICTION / REVIEW REQUIRED */
        ) : isReview ? (
          <div className="flex items-start gap-4">
            <div className="w-11 h-11 rounded-2xl bg-rose-100 flex items-center justify-center shrink-0">
              <AlertOctagon className="w-5 h-5 text-rose-700" />
            </div>
            <div className="flex-1 space-y-3">
              <div>
                <h3 className="text-sm font-bold text-rose-950">
                  These delivery details don't match — human review needed.
                </h3>
                <p className="text-xs text-rose-900/80 mt-1 leading-relaxed">
                  The order lists <strong>Seattle, WA</strong> as the destination, but the available delivery record lists <strong>Portland, OR</strong>.
                  The delivery record is part of our demonstration data and has not been independently checked with the carrier.
                  This discrepancy needs a human to review it — ProofGraph cannot resolve it automatically.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3 p-3 bg-rose-50/80 rounded-xl border border-rose-200/80 text-xs">
                <div>
                  <span className="font-bold text-rose-900 uppercase text-[10px] tracking-wide">Order destination</span>
                  <p className="text-slate-800 font-medium mt-0.5">Seattle, WA</p>
                </div>
                <div>
                  <span className="font-bold text-rose-900 uppercase text-[10px] tracking-wide">Delivery record shows</span>
                  <p className="text-slate-800 font-medium mt-0.5">Portland, OR</p>
                </div>
              </div>

              <button
                onClick={onOpenReviewModal}
                className="px-4 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold flex items-center gap-2 transition-all shadow-sm"
              >
                <FileText className="w-3.5 h-3.5" />
                <span>Review this issue</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

        /* MISSING TRACKING */
        ) : !hasTracking ? (
          <div className="flex items-start gap-4">
            <div className="w-11 h-11 rounded-2xl bg-blue-100 flex items-center justify-center shrink-0">
              <Truck className="w-5 h-5 text-blue-700" />
            </div>
            <div className="flex-1 space-y-4">
              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Add tracking information
                </h3>
                <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                  To check whether this item was delivered, please enter the carrier and tracking number from your shipping records.
                  This will save the tracking details — delivery will not be confirmed automatically until a carrier check is run.
                </p>
              </div>

              <form onSubmit={handleTrackingSubmit} className="space-y-3 max-w-lg">
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="block text-[11px] font-bold text-slate-600 mb-1">Carrier</label>
                    <select
                      value={carrier}
                      onChange={(e) => setCarrier(e.target.value)}
                      className="w-full text-xs rounded-xl border border-slate-300 p-2.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="USPS">USPS</option>
                      <option value="UPS">UPS</option>
                      <option value="FedEx">FedEx</option>
                      <option value="DHL">DHL</option>
                    </select>
                  </div>
                  <div className="col-span-2">
                    <label className="block text-[11px] font-bold text-slate-600 mb-1">Tracking number</label>
                    <input
                      type="text"
                      value={trackingNumber}
                      onChange={(e) => setTrackingNumber(e.target.value)}
                      placeholder="e.g. 940010009999"
                      className="w-full text-xs rounded-xl border border-slate-300 p-2.5 bg-white font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                </div>

                <p className="text-[11px] text-slate-500">
                  After saving, ProofGraph will attempt to check the carrier's delivery record using demonstration data.
                </p>

                <button
                  type="submit"
                  disabled={submitting || !trackingNumber.trim()}
                  className="px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold flex items-center gap-2 transition-all shadow-sm disabled:opacity-50"
                >
                  {submitting ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Send className="w-3.5 h-3.5" />
                  )}
                  <span>{submitting ? "Saving…" : "Save tracking information"}</span>
                </button>
              </form>
            </div>
          </div>

        /* TRACKING ON FILE, NOT YET CHECKED */
        ) : !isCarrierVerified ? (
          <div className="flex items-start gap-4">
            <div className="w-11 h-11 rounded-2xl bg-amber-100 flex items-center justify-center shrink-0">
              <Clock className="w-5 h-5 text-amber-700" />
            </div>
            <div className="flex-1 space-y-3">
              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Check delivery with the carrier
                </h3>
                <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                  Tracking number{" "}
                  <span className="font-mono text-slate-800">{shipmentNode?.content?.tracking_number}</span>{" "}
                  was provided by the merchant. ProofGraph can look up the delivery record using demonstration carrier data.
                  This is not a live check — it uses synthetic fixture data for this demo.
                </p>
              </div>

              {/* Require explicit confirmation for the external action */}
              <label className="flex items-start gap-2.5 cursor-pointer group">
                <input
                  type="checkbox"
                  checked={confirmCheck}
                  onChange={(e) => setConfirmCheck(e.target.checked)}
                  className="mt-0.5 w-3.5 h-3.5 rounded border-slate-300 text-amber-600 focus:ring-amber-500"
                />
                <span className="text-xs text-slate-600 group-hover:text-slate-800 transition-colors">
                  I understand this uses demonstration data and is not a live carrier lookup.
                </span>
              </label>

              <button
                onClick={() => { setConfirmCheck(false); onVerifyCarrier(); }}
                disabled={carrierVerifying || !confirmCheck}
                className="px-4 py-2.5 rounded-xl bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold flex items-center gap-2 transition-all shadow-sm disabled:opacity-50"
              >
                {carrierVerifying ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Truck className="w-3.5 h-3.5" />
                )}
                <span>{carrierVerifying ? "Checking…" : "Look up delivery record"}</span>
              </button>
            </div>
          </div>

        /* SNAD — UPLOAD NEEDED */
        ) : dispute.category === "SIGNIFICANTLY_NOT_AS_DESCRIBED" ? (
          <div className="flex items-start gap-4">
            <div className="w-11 h-11 rounded-2xl bg-indigo-100 flex items-center justify-center shrink-0">
              <Upload className="w-5 h-5 text-indigo-700" />
            </div>
            <div className="flex-1 space-y-3">
              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Add a photo or document
                </h3>
                <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                  The customer says the item doesn't match the listing. A clear photo of the item as shipped, or a certificate of authenticity, can support your response.
                </p>
              </div>

              <form onSubmit={handleFileUpload} className="space-y-3 max-w-sm">
                <input
                  type="file"
                  accept="image/*,application/pdf"
                  onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                  className="block w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"
                />
                <button
                  type="submit"
                  disabled={uploading || !selectedFile}
                  className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold flex items-center gap-2 transition-all shadow-sm disabled:opacity-50"
                >
                  {uploading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                  <span>{uploading ? "Saving document…" : "Save document"}</span>
                </button>
              </form>
            </div>
          </div>

        /* FALLBACK */
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-slate-600 leading-relaxed">
              {dispute.current_policy_decision?.chosen_action?.description ||
                "Records are being gathered. Check back shortly for the next recommended step."}
            </p>
            <button
              onClick={onOpenReviewModal}
              className="px-4 py-2 rounded-xl bg-slate-900 text-white text-xs font-semibold flex items-center gap-1.5"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>See case summary</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
