"use client";

import React, { useState } from "react";

type AIClaim = {
  source_id: string;
  quote: string;
  claim_type: string;
  evidence_need: string;
  evidence_question: string;
  inference_node_id?: string | null;
};

type AIResponse = {
  status: string;
  provider: string;
  model: string | null;
  model_called: boolean;
  claims: AIClaim[];
  rejected_items: number;
  message: string;
  provenance: string;
  fallback_action_id: string | null;
};

/** Model output is shown only as a source-grounded candidate, never as verified evidence. */
export function AIClaimsPanel({ disputeId }: { disputeId: string }) {
  const [result, setResult] = useState<AIResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const analyze = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch(
        `/api/v1/disputes/${encodeURIComponent(disputeId)}/ai/extract`,
        { method: "POST" }
      );
      if (!response.ok) {
        setError(response.status === 403
          ? "Reviewer access is required before sending claim text to an external AI provider."
          : "Model extraction could not be started. Investigation decisions are unchanged.");
        return;
      }
      setResult((await response.json()) as AIResponse);
    } catch {
      setError("Model extraction request failed. The deterministic investigation remains available.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label="AI claim extraction" className="bg-white rounded-2xl border border-slate-200 px-5 py-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold text-slate-900">Optional AI claim extraction</h3>
          <p className="text-xs text-slate-600 mt-1">
            Extract exact statements and possible evidence questions using server-configured
            Gemini (default) or OpenAI. No output verifies evidence or changes dispute decisions.
          </p>
        </div>
        <button type="button" onClick={analyze} disabled={busy}
          className="rounded-lg px-4 py-2 bg-indigo-700 text-white text-xs font-semibold disabled:opacity-60 focus-visible:ring-2 focus-visible:ring-indigo-500">
          {busy ? "Analyzing claim text…" : "Analyze dispute text with AI"}
        </button>
      </div>

      {error && <p role="alert" className="text-xs text-rose-700">{error}</p>}
      {result && (
        <div aria-live="polite" className="border-t border-slate-100 pt-3 space-y-3 text-xs">
          <p className="font-semibold text-slate-800">
            {result.model_called
              ? (result.status.startsWith("MODEL_")
                ? `Provider: ${result.provider} · Model: ${result.model ?? "unknown"} · Status: ${result.status}`
                : `Attempted provider: ${result.provider} · Model: ${result.model ?? "unknown"} · No accepted model output · ${result.status}`)
              : `No model call · ${result.status} · Configured provider: ${result.provider}`}
          </p>
          <p className="text-slate-600">{result.message}</p>
          <p className="font-medium text-amber-800">
            {result.provenance}. Verbatim quotes are party statements, not established facts.
          </p>
          {result.claims.map((claim, index) => (
            <article key={claim.inference_node_id || index}
              className="rounded-lg border border-amber-200 bg-amber-50/50 p-3 space-y-1.5">
              <p className="font-semibold text-slate-800">{claim.claim_type.replace(/_/g, " ")}</p>
              <blockquote className="text-slate-800 italic">&ldquo;{claim.quote}&rdquo;</blockquote>
              <p className="text-slate-600">
                Exact source: <code className="font-mono">{claim.source_id}</code>
              </p>
              <p className="text-slate-700">Possible evidence question: {claim.evidence_question}</p>
              {claim.inference_node_id && (
                <p className="text-slate-500">
                  Graph node: <code className="font-mono">{claim.inference_node_id}</code> ·
                  MODEL_INFERENCE · UNVERIFIED
                </p>
              )}
            </article>
          ))}
          {result.rejected_items > 0 && (
            <p className="text-amber-800">
              {result.rejected_items} model item(s) excluded because they could not be validated.
            </p>
          )}
          {result.fallback_action_id && (
            <p className="text-slate-600">
              Separate deterministic investigation action: <code>{result.fallback_action_id}</code>
            </p>
          )}
          {result.claims.length > 0 && (
            <p className="text-slate-500">
              Candidate claims have been recorded in the graph with unverified model provenance.
              Refresh the case to inspect their source links in &ldquo;How we checked&rdquo;.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
