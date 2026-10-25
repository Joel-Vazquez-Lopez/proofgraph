"use client";

import React, { useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  Node,
  Edge,
  MarkerType,
} from "@xyflow/react";
import {
  Scale,
  CreditCard,
  User,
  ShoppingBag,
  Truck,
  Eye,
  HelpCircle,
  FileCheck2,
  AlertOctagon,
  CheckCircle2,
  Clock,
  Sparkles,
} from "lucide-react";

export interface GraphNodeData {
  id: string;
  type: string;
  label: string;
  content: Record<string, any>;
  source: string;
  origin?: string;
  verification_status: string;
  created_at: string;
  verified_at?: string;
}

export interface GraphEdgeData {
  id: string;
  source_id: string;
  target_id: string;
  type: string;
  provenance: string;
}

interface EvidenceGraphViewProps {
  nodes: GraphNodeData[];
  edges: GraphEdgeData[];
  selectedNodeId?: string | null;
  onSelectNode?: (node: GraphNodeData) => void;
}

export const EvidenceGraphView: React.FC<EvidenceGraphViewProps> = ({
  nodes,
  edges,
  selectedNodeId,
  onSelectNode,
}) => {
  // Compute positions dynamically in an expansive hierarchical DAG layout
  const flowNodes: Node[] = useMemo(() => {
    // Organize by logical investigation tiers
    const layerMapping: Record<string, number> = {
      DISPUTE: 0,
      TRANSACTION: 0,
      CLAIM: 1,
      ORDER: 1,
      QUESTION: 2,
      SHIPMENT: 2,
      OBSERVATION: 3,
      EVIDENCE_ITEM: 3,
    };

    const typeOrder: Record<string, number> = {
      DISPUTE: 0,
      TRANSACTION: 1,
      ORDER: 0,
      CLAIM: 1,
      SHIPMENT: 0,
      QUESTION: 1,
      OBSERVATION: 0,
      EVIDENCE_ITEM: 1,
    };

    const layerItems: Record<number, GraphNodeData[]> = { 0: [], 1: [], 2: [], 3: [] };

    nodes.forEach((n) => {
      const layer = layerMapping[n.type] ?? 2;
      layerItems[layer].push(n);
    });

    // Sort nodes within each layer for consistent visual grouping
    Object.keys(layerItems).forEach((layerKey) => {
      const l = Number(layerKey);
      layerItems[l].sort((a, b) => (typeOrder[a.type] ?? 0) - (typeOrder[b.type] ?? 0));
    });

    const resultNodes: Node[] = [];

    Object.entries(layerItems).forEach(([layerStr, layerNodes]) => {
      const layer = Number(layerStr);
      const totalInLayer = layerNodes.length;
      const layerWidth = totalInLayer * 340;
      const startX = Math.max(40, (1100 - layerWidth) / 2);

      layerNodes.forEach((n, idx) => {
        const x = startX + idx * 350;
        const y = 40 + layer * 165;
        const isSelected = selectedNodeId === n.id;

        // Visual theme based on node type
        let borderClass = "border-slate-200 hover:border-slate-400";
        let headerBg = "bg-slate-50 text-slate-700";
        let icon = <Scale className="w-3.5 h-3.5" />;

        if (n.type === "DISPUTE") {
          borderClass = "border-blue-400 shadow-blue-50/50";
          headerBg = "bg-blue-50 text-blue-800 border-b border-blue-100";
          icon = <Scale className="w-3.5 h-3.5 text-blue-600" />;
        } else if (n.type === "TRANSACTION") {
          borderClass = "border-emerald-400 shadow-emerald-50/50";
          headerBg = "bg-emerald-50 text-emerald-800 border-b border-emerald-100";
          icon = <CreditCard className="w-3.5 h-3.5 text-emerald-600" />;
        } else if (n.type === "ORDER") {
          borderClass = "border-teal-400 shadow-teal-50/50";
          headerBg = "bg-teal-50 text-teal-800 border-b border-teal-100";
          icon = <ShoppingBag className="w-3.5 h-3.5 text-teal-600" />;
        } else if (n.type === "CLAIM") {
          borderClass = "border-amber-400 shadow-amber-50/50";
          headerBg = "bg-amber-50 text-amber-800 border-b border-amber-100";
          icon = <User className="w-3.5 h-3.5 text-amber-600" />;
        } else if (n.type === "SHIPMENT") {
          borderClass = "border-cyan-400 shadow-cyan-50/50";
          headerBg = "bg-cyan-50 text-cyan-800 border-b border-cyan-100";
          icon = <Truck className="w-3.5 h-3.5 text-cyan-600" />;
        } else if (n.type === "OBSERVATION") {
          borderClass = "border-indigo-400 shadow-indigo-50/50";
          headerBg = "bg-indigo-50 text-indigo-800 border-b border-indigo-100";
          icon = <Eye className="w-3.5 h-3.5 text-indigo-600" />;
        } else if (n.type === "QUESTION") {
          borderClass = "border-purple-400 shadow-purple-50/50";
          headerBg = "bg-purple-50 text-purple-800 border-b border-purple-100";
          icon = <HelpCircle className="w-3.5 h-3.5 text-purple-600" />;
        } else if (n.type === "EVIDENCE_ITEM") {
          borderClass = "border-sky-400 shadow-sky-50/50";
          headerBg = "bg-sky-50 text-sky-800 border-b border-sky-100";
          icon = <FileCheck2 className="w-3.5 h-3.5 text-sky-600" />;
        }

        // Status badge colors
        const status = n.verification_status;
        let statusBadge = (
          <span className="flex items-center gap-1 text-[10px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
            <Clock className="w-2.5 h-2.5" /> {status}
          </span>
        );
        if (status === "VERIFIED") {
          statusBadge = (
            <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-700 bg-emerald-100/80 px-2 py-0.5 rounded-full">
              <CheckCircle2 className="w-2.5 h-2.5" /> Verified
            </span>
          );
        } else if (status === "CONTRADICTED") {
          statusBadge = (
            <span className="flex items-center gap-1 text-[10px] font-bold text-rose-700 bg-rose-100 px-2 py-0.5 rounded-full animate-pulse">
              <AlertOctagon className="w-2.5 h-2.5" /> Contradiction
            </span>
          );
        } else if (status === "UNVERIFIED") {
          statusBadge = (
            <span className="flex items-center gap-1 text-[10px] font-semibold text-amber-700 bg-amber-100/80 px-2 py-0.5 rounded-full">
              <Clock className="w-2.5 h-2.5" /> Unverified
            </span>
          );
        }

        resultNodes.push({
          id: n.id,
          position: { x, y },
          data: {
            label: (
              <div
                onClick={() => onSelectNode && onSelectNode(n)}
                className={`w-[290px] rounded-xl border bg-white shadow-sm transition-all duration-150 cursor-pointer text-left overflow-hidden ${borderClass} ${
                  isSelected
                    ? "ring-2 ring-blue-600 shadow-md scale-[1.02]"
                    : "hover:shadow-md hover:-translate-y-0.5"
                }`}
              >
                {/* Header row */}
                <div className={`px-3 py-1.5 flex items-center justify-between text-xs font-semibold ${headerBg}`}>
                  <div className="flex items-center gap-1.5">
                    {icon}
                    <span className="text-[11px] font-bold uppercase tracking-wider">
                      {n.type.replace(/_/g, " ")}
                    </span>
                  </div>
                  <span className="text-[10px] font-mono opacity-80 truncate max-w-[110px]" title={n.source}>
                    {n.source}
                  </span>
                </div>

                {/* Body content */}
                <div className="p-3">
                  <p className="text-xs font-bold text-slate-900 leading-snug line-clamp-2">
                    {n.label}
                  </p>

                  {/* Summary content preview */}
                  <div className="mt-2 text-[11px] text-slate-600 bg-slate-50/80 rounded-md p-1.5 border border-slate-100 line-clamp-2 font-mono">
                    {n.content?.amount ? (
                      <span>${Number(n.content.amount).toFixed(2)} {n.content.currency || "USD"}</span>
                    ) : n.content?.status ? (
                      <span>Status: {String(n.content.status)}</span>
                    ) : n.content?.tracking_number ? (
                      <span>Tracking: {String(n.content.tracking_number)}</span>
                    ) : n.content?.destination_address?.postal_code ? (
                      <span>ZIP: {String(n.content.destination_address.postal_code)}</span>
                    ) : n.content?.text ? (
                      <span className="italic font-sans">&quot;{String(n.content.text).slice(0, 50)}...&quot;</span>
                    ) : (
                      <span className="font-sans text-slate-400">Node details available</span>
                    )}
                  </div>

                  {/* Footer status & provenance */}
                  <div className="mt-2.5 pt-2 border-t border-slate-100 flex items-center justify-between text-[10px]">
                    <span className="text-slate-400 font-medium">
                      {n.origin ? (
                        <span className="text-slate-500 font-mono text-[9px] uppercase">
                          {n.origin.replace(/_/g, " ")}
                        </span>
                      ) : (
                        "Provenance"
                      )}
                    </span>
                    {statusBadge}
                  </div>
                </div>
              </div>
            ),
          },
        });
      });
    });

    return resultNodes;
  }, [nodes, selectedNodeId, onSelectNode]);

  // Clean, non-colliding edges with distinct semantic colors
  const flowEdges: Edge[] = useMemo(() => {
    return edges.map((e) => {
      let strokeColor = "#94a3b8"; // Slate-400
      let strokeWidth = 2;
      let strokeDash = undefined;
      let animated = false;
      let labelBg = "#ffffff";
      let labelColor = "#475569";
      let labelText = e.type.replace(/_/g, " ").toLowerCase();

      if (e.type === "CONTRADICTS") {
        strokeColor = "#e11d48"; // Rose-600
        strokeWidth = 2.5;
        animated = true;
        labelColor = "#e11d48";
        labelBg = "#ffe4e6";
        labelText = "⚠️ Contradicts";
      } else if (e.type === "SUPPORTS") {
        strokeColor = "#059669"; // Emerald-600
        labelColor = "#059669";
        labelBg = "#ecfdf5";
        labelText = "✓ Supports";
      } else if (e.type === "DERIVED_FROM") {
        strokeColor = "#4f46e5"; // Indigo-600
        strokeDash = "4 4";
        labelColor = "#4f46e5";
        labelText = "Derived";
      } else if (e.type === "ANSWERS") {
        strokeColor = "#9333ea"; // Purple-600
        animated = true;
        labelColor = "#9333ea";
        labelText = "Answers";
      } else if (e.type === "REFERENCES") {
        strokeColor = "#64748b";
        labelText = "References";
      }

      return {
        id: e.id,
        source: e.source_id,
        target: e.target_id,
        label: labelText,
        type: "smoothstep",
        animated,
        style: {
          stroke: strokeColor,
          strokeWidth,
          strokeDasharray: strokeDash,
        },
        labelStyle: {
          fontSize: 10,
          fontWeight: 700,
          fill: labelColor,
        },
        labelBgStyle: {
          fill: labelBg,
          fillOpacity: 0.95,
          rx: 4,
          ry: 4,
        },
        labelBgPadding: [6, 2] as [number, number],
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: strokeColor,
          width: 14,
          height: 14,
        },
      };
    });
  }, [edges]);

  return (
    <div className="w-full h-[560px] bg-slate-900/5 rounded-2xl border border-slate-200 overflow-hidden relative shadow-inner">
      {/* Top Legend Bar */}
      <div className="absolute top-3 left-3 z-10 bg-white/95 backdrop-blur-md px-3.5 py-1.5 rounded-lg border border-slate-200/90 text-xs shadow-sm flex items-center gap-4 text-slate-700">
        <span className="font-bold text-slate-900 flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5 text-blue-600" /> Legend:
        </span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-blue-500 inline-block" /> Dispute</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" /> Transaction</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-teal-500 inline-block" /> Order</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" /> Claim</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-cyan-500 inline-block" /> Shipment</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-indigo-500 inline-block" /> Carrier Observation</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-rose-600 inline-block animate-pulse" /> Contradiction</span>
      </div>

      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        attributionPosition="bottom-right"
        minZoom={0.4}
        maxZoom={1.5}
      >
        <Background gap={20} size={1} color="#cbd5e1" />
        <Controls className="bg-white/90 border border-slate-200 shadow-sm rounded-lg" />
      </ReactFlow>
    </div>
  );
};
