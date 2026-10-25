"use client";

import React, { useState } from "react";
import {
  GitBranch,
  History,
  Activity,
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Sparkles,
  Info,
  ChevronDown,
  ChevronUp,
  X,
  ExternalLink,
  Code,
  Lock,
} from "lucide-react";
import { EvidenceGraphView, GraphNodeData } from "./EvidenceGraphView";

interface AdvancedWorkspaceProps {
  dispute: any;
  isOpen: boolean;
  onToggle: () => void;
  selectedNode: GraphNodeData | null;
  onSelectNode: (node: GraphNodeData | null) => void;
}

export const AdvancedWorkspace: React.FC<AdvancedWorkspaceProps> = ({
  dispute,
  isOpen,
  onToggle,
  selectedNode,
  onSelectNode,
}) => {
  const [activeSubTab, setActiveSubTab] = useState<"graph" | "timeline" | "diagnostics">("graph");

  if (!dispute) return null;

  const nodes = dispute.evidence_graph?.nodes || [];
  const edges = dispute.evidence_graph?.edges || [];
  const timeline = dispute.timeline || [];
  const integrityFindings = dispute.integrity_findings || [];
  const policy = dispute.current_policy_decision;

  // Provenance breakdown counts
  const provenanceStats = nodes.reduce((acc: any, node: any) => {
    const origin = node.origin || "UNSPECIFIED";
    acc[origin] = (acc[origin] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden transition-all duration-300">
      {/* Collapsible Header Banner */}
      <button
        onClick={onToggle}
        className="w-full px-5 py-4 flex items-center justify-between text-left hover:bg-slate-50/80 transition-colors border-b border-slate-100"
      >
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-700">
            <GitBranch className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-900">
                How we checked
              </h3>
              <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">
                Advanced
              </span>
            </div>
            <p className="text-xs text-slate-500">
              Evidence graph ({nodes.length} items), source records, and activity history for this case
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 text-slate-500">
          <span className="text-xs font-semibold text-slate-600 hidden sm:inline">
            {isOpen ? "Hide details" : "How we checked"}
          </span>
          {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </button>

      {/* Expanded Content Area */}
      {isOpen && (
        <div className="p-5 space-y-5 animate-in slide-in-from-top-2 duration-200">
          {/* Sub-tab navigation */}
          <div className="flex items-center justify-between border-b border-slate-200 pb-2">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setActiveSubTab("graph")}
                className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-colors flex items-center gap-1.5 ${
                  activeSubTab === "graph"
                    ? "bg-indigo-600 text-white shadow-2xs"
                    : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                }`}
              >
                <GitBranch className="w-3.5 h-3.5" />
                <span>Evidence graph ({nodes.length})</span>
              </button>

              <button
                onClick={() => setActiveSubTab("timeline")}
                className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-colors flex items-center gap-1.5 ${
                  activeSubTab === "timeline"
                    ? "bg-indigo-600 text-white shadow-2xs"
                    : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                }`}
              >
                <History className="w-3.5 h-3.5" />
                <span>Activity history ({timeline.length})</span>
              </button>

              <button
                onClick={() => setActiveSubTab("diagnostics")}
                className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-colors flex items-center gap-1.5 ${
                  activeSubTab === "diagnostics"
                    ? "bg-indigo-600 text-white shadow-2xs"
                    : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                }`}
              >
                <Activity className="w-3.5 h-3.5" />
                <span>Evidence sources</span>
              </button>
            </div>

            <div className="text-[11px] text-slate-400 font-mono hidden md:block">
              Technical view — for reviewers and evaluators
            </div>
          </div>

          {/* TAB 1: Evidence Graph View with Node Inspector */}
          {activeSubTab === "graph" && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
                {/* Graph Canvas */}
                <div className={`${selectedNode ? "lg:col-span-8" : "lg:col-span-12"} transition-all duration-200`}>
                  <div className="h-[440px] border border-slate-200 rounded-xl overflow-hidden bg-slate-50 relative">
                    <EvidenceGraphView
                      nodes={nodes}
                      edges={edges}
                      selectedNodeId={selectedNode?.id}
                      onSelectNode={(node) => onSelectNode(node)}
                    />
                  </div>
                  <p className="text-[11px] text-slate-500 mt-2 flex items-center gap-1">
                    <Info className="w-3 h-3 text-slate-400" />
                    Click any node to see its source, provenance origin, and raw data attributes.
                  </p>
                </div>

                {/* Node Inspector Drawer */}
                {selectedNode && (
                  <div className="lg:col-span-4 bg-slate-50 border border-slate-200 rounded-xl p-4 flex flex-col justify-between max-h-[440px] overflow-y-auto">
                    <div>
                      <div className="flex items-center justify-between pb-3 border-b border-slate-200">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-slate-200 text-slate-800">
                            {selectedNode.type}
                          </span>
                          <span className="text-xs font-bold text-slate-900 truncate">
                            {selectedNode.label}
                          </span>
                        </div>
                        <button
                          onClick={() => onSelectNode(null)}
                          className="p-1 text-slate-400 hover:text-slate-600 rounded-md hover:bg-slate-200"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      <div className="mt-3 space-y-2.5 text-xs">
                        <div>
                          <span className="text-[10px] font-semibold text-slate-500 uppercase">Verification Status</span>
                          <div className="font-mono text-slate-800 font-bold mt-0.5">
                            {selectedNode.verification_status}
                          </div>
                        </div>

                        <div>
                          <span className="text-[10px] font-semibold text-slate-500 uppercase">Provenance Origin</span>
                          <div className="font-mono text-slate-800 font-bold mt-0.5">
                            {selectedNode.origin || "UNSPECIFIED"}
                          </div>
                        </div>

                        <div>
                          <span className="text-[10px] font-semibold text-slate-500 uppercase">Source</span>
                          <div className="font-mono text-slate-700 mt-0.5 truncate">
                            {selectedNode.source}
                          </div>
                        </div>

                        {selectedNode.verified_at && (
                          <div>
                            <span className="text-[10px] font-semibold text-slate-500 uppercase">Verified At</span>
                            <div className="font-mono text-slate-700 mt-0.5">
                              {new Date(selectedNode.verified_at).toLocaleString()}
                            </div>
                          </div>
                        )}

                        <div>
                          <span className="text-[10px] font-semibold text-slate-500 uppercase">Payload Data</span>
                          <pre className="mt-1 p-2 bg-white rounded-lg border border-slate-200 text-[11px] font-mono text-slate-800 overflow-x-auto max-h-40">
                            {JSON.stringify(selectedNode.content, null, 2)}
                          </pre>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 2: Audit Timeline */}
          {activeSubTab === "timeline" && (
            <div className="space-y-3">
              <div className="border border-slate-200 rounded-xl overflow-hidden bg-slate-50/50 p-4">
                <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-4 flex items-center gap-2">
                  <History className="w-3.5 h-3.5 text-indigo-600" /> Activity history
                </h4>

                <div className="relative pl-6 space-y-6 before:content-[''] before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
                  {timeline.map((event: any, index: number) => (
                    <div key={index} className="relative group">
                      <div className="absolute -left-6 top-1 w-3 h-3 rounded-full border-2 border-white bg-indigo-600 shadow-2xs" />
                      <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-2xs">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-bold text-slate-900">{event.action}</span>
                          <span className="text-[11px] font-mono text-slate-500">
                            {new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-600 mt-1 flex items-center gap-2">
                          <span className="font-semibold text-indigo-700">Actor: {event.actor}</span>
                          <span>•</span>
                          <span className="font-mono text-slate-500">Transition: {event.state_transition}</span>
                        </div>
                        {event.notes && (
                          <p className="text-xs text-slate-700 mt-1.5 bg-slate-50 p-2 rounded-lg border border-slate-100">
                            {event.notes}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: Diagnostics & Provenance Breakdown */}
          {activeSubTab === "diagnostics" && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                  Evidence sources by type
                </span>
                <div className="mt-3 space-y-2">
                  {Object.entries(provenanceStats).map(([origin, count]: any) => (
                    <div key={origin} className="flex items-center justify-between text-xs">
                      <span className="font-mono text-slate-700">{origin}</span>
                      <span className="font-bold px-2 py-0.5 rounded-full bg-white border border-slate-200 text-slate-900">
                        {count} items
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                  Investigation scoring (technical)
                </span>
                <div className="mt-3 space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-600">Information gain:</span>
                    <span className="font-mono font-bold text-indigo-700">
                      {(policy?.chosen_action?.expected_information_gain ?? 0) > 0
                        ? (policy?.chosen_action?.expected_information_gain ?? 0).toFixed(2)
                        : "Not estimated"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-600">Acquisition friction:</span>
                    <span className="font-mono font-bold text-slate-700">
                      {(policy?.chosen_action?.acquisition_friction ?? 0).toFixed(2)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-600">Utility score:</span>
                    <span className="font-mono font-bold text-emerald-700">
                      {(policy?.chosen_action?.utility_score ?? 0).toFixed(2)}
                    </span>
                  </div>
                  <p className="text-[10px] text-slate-400 italic pt-1">
                    These are internal action-ranking values, not confidence scores or calibrated probabilities. "Not estimated" means information gain was not calculated.
                  </p>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                  Data integrity safeguards
                </span>
                <div className="mt-3 space-y-2 text-xs text-slate-600">
                  <p>Demonstration data is isolated from live PayPal cases by design.</p>
                  <p>Uploaded files are checked against their content type before being stored.</p>
                  <p>Evidence provenance is recorded separately from verification status — a tracking number does not become "verified delivery" without an explicit check.</p>
                  <p className="text-[10px] text-slate-400 italic pt-1">Note: these are design-level safeguards in the prototype. They are not independently audited guarantees.</p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
