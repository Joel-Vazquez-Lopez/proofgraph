"use client";

import React, { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Clock, Copy, Download, FileText, Scale, X } from "lucide-react";
import {
  evidenceEntries,
  generateReviewMarkdown,
  humanizeRequirement,
  investigationSummary,
  HUMAN_REVIEW_NOTICE,
} from "@/lib/investigation-report.mjs";

interface ReviewPackageModalProps {
  isOpen: boolean;
  onClose: () => void;
  dispute: any;
  productName: string;
  buyerName: string;
}

export const ReviewPackageModal: React.FC<ReviewPackageModalProps> = ({
  isOpen, onClose, dispute, productName, buyerName,
}) => {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    return () => previouslyFocused.current?.focus();
  }, [isOpen]);

  if (!isOpen || !dispute) return null;

  const { isReady, requirements, missing, contradictions, evidence } = investigationSummary(dispute);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(generateReviewMarkdown(dispute, productName, buyerName));
      setCopied(true);
      setCopyError(null);
    } catch {
      setCopyError("Unable to copy automatically. Use Download case summary instead.");
    }
  };

  const handleDownload = () => {
    const blob = new Blob([generateReviewMarkdown(dispute, productName, buyerName)], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `proofgraph-case-${dispute.dispute_id}.md`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const handleDialogKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
    }
    if (e.key !== "Tab") return;
    const focusable = Array.from(
      e.currentTarget.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], input:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 sm:p-6">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-package-title"
        onKeyDown={handleDialogKeyDown}
        className="bg-white rounded-3xl max-w-3xl w-full shadow-2xl border border-slate-200 overflow-hidden flex flex-col max-h-[90vh]"
      >
        <div className="px-5 sm:px-6 py-5 border-b border-slate-100 flex items-start justify-between gap-3 bg-slate-50">
          <div>
            <h3 id="review-package-title" className="text-base font-bold text-slate-900">Case review package</h3>
            <p className="text-xs text-slate-500 mt-1">
              Case {dispute.dispute_id} · {productName} · {dispute.amount} {dispute.currency}
            </p>
            <p className="text-xs font-semibold text-slate-700 mt-1">
              {isReady ? "Ready for human review" : "Investigation in progress"}
            </p>
          </div>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Close review package"
            className="p-2 rounded-xl text-slate-600 hover:text-slate-900 hover:bg-slate-200 focus-visible:ring-2 focus-visible:ring-blue-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 sm:p-6 overflow-y-auto space-y-6 text-sm">
          <div className="p-4 rounded-2xl border border-blue-200 bg-blue-50 text-blue-950">
            <h4 className="font-bold text-sm">{isReady ? "Ready for a reviewer, not automatically resolved" : "More information or review may be needed"}</h4>
            <p className="text-xs mt-1 leading-relaxed">
              Readiness means the evaluator's requirements are met. It does not prove that individual records are authentic or independently verified.
            </p>
          </div>

          <section aria-labelledby="statements-heading">
            <h4 id="statements-heading" className="text-xs font-bold text-slate-600 uppercase tracking-wider mb-2">What happened — reported statements</h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                <p className="text-[11px] font-bold text-slate-600 uppercase">Customer: {buyerName}</p>
                <p className="text-xs text-slate-800 mt-1">{dispute.buyer_claim || "No customer statement recorded."}</p>
              </div>
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                <p className="text-[11px] font-bold text-slate-600 uppercase">Merchant statement</p>
                <p className="text-xs text-slate-800 mt-1">{dispute.seller_response || "No merchant statement recorded."}</p>
              </div>
            </div>
          </section>

          <section aria-labelledby="evidence-heading">
            <h4 id="evidence-heading" className="text-xs font-bold text-slate-600 uppercase tracking-wider mb-2">
              Evidence on file and where it comes from
            </h4>
            <p className="text-xs text-slate-600 mb-3">
              Source labels distinguish simulation, submitted records, inferences and independently verified evidence.
            </p>
            {evidence.length ? (
              <ul className="space-y-2">
                {evidence.map((record: any, index: number) => (
                  <li key={record.id || index} className="bg-slate-50 border border-slate-200 rounded-xl p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-xs font-semibold text-slate-900">{record.title}</p>
                      <span className={`px-2 py-0.5 rounded-full border text-[10px] font-bold ${record.externallyVerified
                        ? "bg-emerald-50 text-emerald-900 border-emerald-200"
                        : "bg-amber-50 text-amber-900 border-amber-200"}`}>
                        {record.label}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-600 mt-1">{record.description}</p>
                    <p className="text-[11px] text-slate-500 mt-1">Source: {record.source} · Verification: {record.verification}</p>
                  </li>
                ))}
              </ul>
            ) : <p className="text-xs text-slate-600 bg-slate-50 p-3 rounded-xl">No evidence items available for this case.</p>}
          </section>

          <section aria-labelledby="requirements-heading">
            <h4 id="requirements-heading" className="text-xs font-bold text-slate-600 uppercase tracking-wider mb-2">
              Evaluator requirements marked satisfied
            </h4>
            <p className="text-xs text-slate-600 mb-2">These are readiness checks, not independently verified facts.</p>
            {requirements.length ? (
              <ul className="space-y-1.5">{requirements.map((req: string, i: number) => (
                <li key={i} className="text-xs bg-slate-50 border border-slate-200 rounded-lg p-2">{humanizeRequirement(req)}</li>
              ))}</ul>
            ) : <p className="text-xs text-slate-600">No satisfied requirements reported.</p>}
          </section>

          <section aria-labelledby="outstanding-heading">
            <h4 id="outstanding-heading" className="text-xs font-bold text-slate-600 uppercase tracking-wider mb-2">What remains unresolved</h4>
            {contradictions.length > 0 && (
              <ul className="space-y-2 mb-2">{contradictions.map((c: string, i: number) => (
                <li key={i} className="flex gap-2 items-start bg-rose-50 border border-rose-200 rounded-lg p-3 text-xs text-rose-950">
                  <AlertTriangle className="w-4 h-4 shrink-0" /><span>Conflicting evidence: {c}</span>
                </li>
              ))}</ul>
            )}
            {missing.length > 0 && (
              <ul className="space-y-2">{missing.map((m: string, i: number) => (
                <li key={i} className="flex gap-2 items-start bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-950">
                  <Clock className="w-4 h-4 shrink-0" /><span>Still needed: {humanizeRequirement(m)}</span>
                </li>
              ))}</ul>
            )}
            {!contradictions.length && !missing.length && (
              <p className="text-xs text-slate-600">The evaluator lists no open contradictions or missing requirements. This is not independent confirmation of all facts.</p>
            )}
          </section>

          <section aria-labelledby="assessment-heading" className="bg-slate-50 rounded-xl border border-slate-200 p-3">
            <h4 id="assessment-heading" className="text-xs font-bold text-slate-700 uppercase">Current assessment</h4>
            <p className="text-xs text-slate-800 mt-1">{dispute.readiness?.rationale || "No assessment rationale available."}</p>
            <p className="text-xs text-slate-500 mt-2">Recommended state: {dispute.readiness?.recommended_state || dispute.state || "Not supplied"}</p>
          </section>

          <div className="flex items-start gap-2.5 bg-blue-50 border border-blue-200 rounded-xl p-3.5 text-xs text-blue-950">
            <Scale className="w-4 h-4 shrink-0" /><p>{HUMAN_REVIEW_NOTICE}</p>
          </div>
        </div>

        <div className="px-5 sm:px-6 py-4 bg-slate-50 border-t border-slate-200 flex flex-wrap justify-between items-center gap-3">
          <p className="text-[11px] text-slate-500">{evidence.length} evidence records · {dispute.timeline?.length || 0} activity events</p>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={handleCopy}
              className="px-3 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-100 text-slate-700 text-xs font-semibold flex items-center gap-1.5">
              {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              {copied ? "Copied" : "Copy summary"}
            </button>
            <button type="button" onClick={handleDownload}
              className="px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold flex items-center gap-1.5">
              <Download className="w-3.5 h-3.5" /> Download case summary
            </button>
          </div>
          {copyError && <p role="alert" className="basis-full text-xs text-rose-700">{copyError}</p>}
        </div>
      </div>
    </div>
  );
};
