"use client";

import React, { useState } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  FileText,
  Download,
  Copy,
  Check,
  X,
  ShieldCheck,
  Clock,
  ArrowRight,
  Scale,
  Sparkles,
} from "lucide-react";

interface ReviewPackageModalProps {
  isOpen: boolean;
  onClose: () => void;
  dispute: any;
  productName: string;
  buyerName: string;
}

export const ReviewPackageModal: React.FC<ReviewPackageModalProps> = ({
  isOpen,
  onClose,
  dispute,
  productName,
  buyerName,
}) => {
  const [copied, setCopied] = useState(false);

  if (!isOpen || !dispute) return null;

  const isReady = dispute.readiness?.is_decision_ready || dispute.is_decision_ready;
  const satisfiedReqs = dispute.readiness?.satisfied_requirements || [];
  const missingReqs = dispute.readiness?.missing_requirements || [];
  const contradictions = dispute.readiness?.active_contradictions || [];

  // Generate markdown report for export
  const generateMarkdownReport = (): string => {
    return `# ProofGraph Dispute Investigation Summary
**Case ID**: ${dispute.dispute_id}
**Transaction ID**: ${dispute.transaction_id || "N/A"}
**Product**: ${productName}
**Amount**: $${dispute.amount.toFixed(2)} ${dispute.currency}
**Buyer**: ${buyerName} (${dispute.buyer_id})
**Seller**: ${dispute.seller_id}
**Status**: ${isReady ? "READY FOR REVIEW" : "IN PROGRESS"}
**Date Generated**: ${new Date().toISOString()}

---

## 1. What Happened
- **Buyer Claim**: "${dispute.buyer_claim || "Item not received"}"
- **Seller Response**: "${dispute.seller_response || "Tracking and fulfillment records provided."}"

---

## 2. Established & Verified Facts
${satisfiedReqs.length > 0
  ? satisfiedReqs.map((req: string) => `- [x] ${req.replace(/_/g, " ")}: Verified`).join("\n")
  : "- Order placement and payment verified on ledger"}

---

## 3. Outstanding Questions & Discrepancies
${contradictions.length > 0
  ? contradictions.map((c: string) => `- [!] CONTRADICTION: ${c}`).join("\n")
  : "- None detected; facts are mutually consistent"}
${missingReqs.length > 0
  ? missingReqs.map((m: string) => `- [ ] Missing requirement: ${m.replace(/_/g, " ")}`).join("\n")
  : ""}

---

## 4. Policy & Audit Integrity
- **Engine Recommendation**: ${dispute.readiness?.recommended_state || dispute.state}
- **Rationale**: ${dispute.readiness?.rationale || "All required evidentiary standards met."}
- **Total Evidence Nodes**: ${dispute.evidence_graph?.nodes?.length || 0}
- **Total Audited Steps**: ${dispute.timeline?.length || 0}

---

> **Notice**: ProofGraph is an evidence-assembly and verification system. It does not decide dispute outcomes or move funds. All decisions are rendered by authorized human adjudicators.
`;
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(generateMarkdownReport());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const report = generateMarkdownReport();
    const blob = new Blob([report], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `proofgraph-case-${dispute.dispute_id}.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-200">
      <div className="bg-white rounded-3xl max-w-3xl w-full shadow-2xl border border-slate-200 overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between bg-gradient-to-r from-slate-50 via-white to-slate-50">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-2xl flex items-center justify-center ${
              isReady ? "bg-emerald-100 text-emerald-800" : "bg-blue-100 text-blue-800"
            }`}>
              {isReady ? <ShieldCheck className="w-5 h-5" /> : <FileText className="w-5 h-5" />}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-slate-900">
                  Case Review Package
                </h3>
                <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${
                  isReady ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
                }`}>
                  {isReady ? "Ready for Review" : "In Progress"}
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Case {dispute.dispute_id} • {productName} (${dispute.amount.toFixed(2)} {dispute.currency})
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Body */}
        <div className="p-6 overflow-y-auto space-y-6 text-sm">
          {/* Main Status Headline */}
          <div className={`p-4 rounded-2xl border ${
            isReady
              ? "bg-emerald-50/80 border-emerald-200/80 text-emerald-950"
              : "bg-amber-50/80 border-amber-200/80 text-amber-950"
          }`}>
            <div className="flex items-start gap-3">
              {isReady ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-600 mt-0.5 shrink-0" />
              ) : (
                <Clock className="w-5 h-5 text-amber-600 mt-0.5 shrink-0" />
              )}
              <div>
                <h4 className="font-bold text-sm">
                  {isReady
                    ? "This case is ready for a human reviewer."
                    : "Still gathering records — not yet ready for review."}
                </h4>
                <p className="text-xs mt-1 leading-relaxed opacity-90">
                  {isReady
                    ? "The available records have been gathered and checked against our demonstration data. A human reviewer will make the final decision. ProofGraph does not decide dispute outcomes."
                    : "Some records or clarifications are still needed before this case can be sent for review."}
                </p>
              </div>
            </div>
          </div>

          {/* Factual Summary: What happened */}
          <div>
            <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2.5">
              What happened
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80">
                <span className="text-[11px] font-bold text-slate-500 uppercase">Customer statement</span>
                <p className="text-xs text-slate-800 font-medium mt-1">
                  "{dispute.buyer_claim || "Buyer claims item did not arrive."}"
                </p>
                <p className="text-[11px] text-slate-500 mt-2">
                  Reported by: {buyerName}
                </p>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80">
                <span className="text-[11px] font-bold text-slate-500 uppercase">Merchant record</span>
                <p className="text-xs text-slate-800 font-medium mt-1">
                  "{dispute.seller_response || "Tracking and order records provided."}"
                </p>
                <p className="text-[11px] text-slate-500 mt-2">
                  Seller: {dispute.seller_id}
                </p>
              </div>
            </div>
          </div>

          {/* On record vs Open questions */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2.5 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> On record
              </h4>
              <ul className="space-y-2">
                <li className="flex items-start gap-2 text-xs text-slate-700 bg-slate-50 p-2.5 rounded-xl border border-slate-200/60">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 mt-0.5 shrink-0" />
                  <span>Order placed and ${dispute.amount.toFixed(2)} paid via PayPal</span>
                </li>
                {satisfiedReqs.map((req: string, idx: number) => (
                  <li key={idx} className="flex items-start gap-2 text-xs text-slate-700 bg-slate-50 p-2.5 rounded-xl border border-slate-200/60">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 mt-0.5 shrink-0" />
                    <span>{req.replace(/_/g, " ")}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2.5 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-600" /> Not yet confirmed
              </h4>
              <div className="space-y-2">
                {contradictions.length > 0 ? (
                  contradictions.map((c: string, idx: number) => (
                    <div key={idx} className="flex items-start gap-2 text-xs text-rose-800 bg-rose-50 p-2.5 rounded-xl border border-rose-200">
                      <AlertTriangle className="w-3.5 h-3.5 text-rose-600 mt-0.5 shrink-0" />
                      <span><strong>These details don't match:</strong> {c}</span>
                    </div>
                  ))
                ) : missingReqs.length > 0 ? (
                  missingReqs.map((m: string, idx: number) => (
                    <div key={idx} className="flex items-start gap-2 text-xs text-amber-800 bg-amber-50 p-2.5 rounded-xl border border-amber-200">
                      <Clock className="w-3.5 h-3.5 text-amber-600 mt-0.5 shrink-0" />
                      <span>Still needed: {m.replace(/_/g, " ")}</span>
                    </div>
                  ))
                ) : (
                  <div className="flex items-start gap-2 text-xs text-emerald-800 bg-emerald-50/50 p-2.5 rounded-xl border border-emerald-100">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 mt-0.5 shrink-0" />
                    <span>No open questions. All required records are in.</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Human authority notice */}
          <div className="p-3.5 rounded-2xl bg-blue-50/80 border border-blue-200/80 text-blue-900 text-xs">
            <div className="flex items-start gap-2.5">
              <Scale className="w-4 h-4 text-blue-700 mt-0.5 shrink-0" />
              <div>
                <p className="font-bold">Decision by a human reviewer</p>
                <p className="mt-0.5 text-blue-800/90 leading-relaxed">
                  ProofGraph gathers and organizes records so a reviewer can make a fast, fair decision.
                  <strong> The AI does not decide dispute outcomes or move funds.</strong> All outcomes require human authorization.
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between gap-3">
          <div className="text-xs text-slate-500">
            {dispute.evidence_graph?.nodes?.length || 0} evidence items • {dispute.timeline?.length || 0} recorded actions
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="px-3.5 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-2xs"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? "Copied" : "Copy summary"}</span>
            </button>

            <button
              onClick={handleDownload}
              className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-xs"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download case summary</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
