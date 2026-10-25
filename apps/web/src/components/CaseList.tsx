"use client";

import React, { useMemo, useState } from "react";
import {
  Search,
  CheckCircle2,
  AlertTriangle,
  Clock,
  ArrowRight,
  ShoppingBag,
  AlertOctagon,
  ChevronRight,
  Filter,
} from "lucide-react";

export interface DisputeSummaryData {
  dispute_id: string;
  category: string;
  state: string;
  data_source: string;
  amount: number;
  currency: string;
  buyer_id: string;
  seller_id: string;
  created_at: string;
  updated_at: string;
  open_questions_count: number;
  is_decision_ready: boolean;
  item_name?: string;
  buyer_name?: string;
}

interface CaseListProps {
  disputes: DisputeSummaryData[];
  selectedId: string;
  onSelectCase: (disputeId: string) => void;
}

export const CaseList: React.FC<CaseListProps> = ({
  disputes,
  selectedId,
  onSelectCase,
}) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [filterState, setFilterState] = useState<"all" | "action" | "review" | "ready">("all");

  // Transform technical state into human-friendly wording and explanations
  const getHumanCaseMeta = (d: DisputeSummaryData) => {
    const isReady = d.is_decision_ready;
    const isReview = d.state === "REVIEW_REQUIRED";
    const isAwaiting = d.state === "AWAITING_EVIDENCE";
    const isInvestigating = d.state === "INVESTIGATING";

    let statusLabel = "Waiting for information";
    let statusClass = "bg-amber-100/80 text-amber-900 border-amber-200";
    let statusIcon = <Clock className="w-3 h-3 text-amber-700" />;

    if (isReady) {
      statusLabel = "Ready for review";
      statusClass = "bg-emerald-100/80 text-emerald-900 border-emerald-200";
      statusIcon = <CheckCircle2 className="w-3 h-3 text-emerald-700" />;
    } else if (isReview) {
      statusLabel = "These details don't match";
      statusClass = "bg-rose-100/80 text-rose-900 border-rose-200";
      statusIcon = <AlertOctagon className="w-3 h-3 text-rose-700" />;
    } else if (isInvestigating) {
      statusLabel = "Investigating";
      statusClass = "bg-blue-100/80 text-blue-900 border-blue-200";
      statusIcon = <Clock className="w-3 h-3 text-blue-700" />;
    }

    // Dynamic, plain-English one-line explanation of what is needed
    let oneLineNeed = "Gathering transaction records";
    if (d.dispute_id === "PP-D-INR-8841") {
      oneLineNeed = isReady
        ? "All delivery records gathered; ready for adjudicator review"
        : "Need shipping tracking number from seller to check delivery";
    } else if (d.dispute_id === "PP-D-INR-9923") {
      oneLineNeed = "Delivery address does not match order destination (Seattle vs Portland)";
    } else if (d.dispute_id === "PP-D-SNAD-3012") {
      oneLineNeed = "Need photos of the delivered watch to verify condition claim";
    } else if (d.dispute_id === "PP-D-DUP-4044") {
      oneLineNeed = "Checking transaction ledger for duplicate settlement record";
    } else {
      if (isReady) oneLineNeed = "Ready for human review";
      else if (isReview) oneLineNeed = "Human review needed to resolve evidence discrepancy";
      else if (isAwaiting) oneLineNeed = "Waiting for information from seller or carrier";
    }

    // Default item name fallback if not present
    const productName = d.item_name || (
      d.dispute_id === "PP-D-INR-8841"
        ? "Keychron Q1 Pro Mechanical Keyboard"
        : d.dispute_id === "PP-D-INR-9923"
        ? "Sony WH-1000XM5 Noise Canceling Headphones"
        : d.dispute_id === "PP-D-SNAD-3012"
        ? "1972 Vintage Chronograph Watch"
        : d.dispute_id === "PP-D-DUP-4044"
        ? "Pro Cloud Hosting (Annual)"
        : "Purchased Item"
    );

    const buyerDisplayName = d.buyer_name || d.buyer_id.replace(/^payer_/, "").replace(/_\d+$/, "").replace(/_/g, " ");

    return {
      productName,
      buyerDisplayName,
      statusLabel,
      statusClass,
      statusIcon,
      oneLineNeed,
      isReview,
      isReady,
      isAwaiting,
    };
  };

  const filteredDisputes = useMemo(() => {
    return disputes.filter((d) => {
      const meta = getHumanCaseMeta(d);
      const matchesSearch =
        meta.productName.toLowerCase().includes(searchQuery.toLowerCase()) ||
        meta.buyerDisplayName.toLowerCase().includes(searchQuery.toLowerCase()) ||
        d.dispute_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        meta.oneLineNeed.toLowerCase().includes(searchQuery.toLowerCase());

      if (!matchesSearch) return false;

      if (filterState === "ready") return d.is_decision_ready;
      if (filterState === "review") return d.state === "REVIEW_REQUIRED";
      if (filterState === "action") return !d.is_decision_ready && d.state !== "REVIEW_REQUIRED";
      return true;
    });
  }, [disputes, searchQuery, filterState]);

  return (
    <div className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-xs space-y-3">
      {/* Header & count */}
      <div className="flex items-center justify-between pb-1">
        <div>
          <h2 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <ShoppingBag className="w-4 h-4 text-blue-600" /> My Cases
          </h2>
          <p className="text-[11px] text-slate-500">
            {disputes.length} active transaction {disputes.length === 1 ? "case" : "cases"} under investigation
          </p>
        </div>
      </div>

      {/* Search Input */}
      <div className="relative">
        <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search by product, buyer, or case..."
          className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl border border-slate-200 bg-slate-50/70 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600 transition-all placeholder:text-slate-400"
        />
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-1 overflow-x-auto pb-1 text-[11px] font-semibold border-b border-slate-100">
        <button
          onClick={() => setFilterState("all")}
          className={`px-2.5 py-1 rounded-lg transition-colors ${
            filterState === "all" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
          }`}
        >
          All ({disputes.length})
        </button>
        <button
          onClick={() => setFilterState("action")}
          className={`px-2.5 py-1 rounded-lg transition-colors ${
            filterState === "action" ? "bg-amber-600 text-white" : "text-amber-700 hover:bg-amber-50"
          }`}
        >
          Waiting for Info
        </button>
        <button
          onClick={() => setFilterState("review")}
          className={`px-2.5 py-1 rounded-lg transition-colors ${
            filterState === "review" ? "bg-rose-600 text-white" : "text-rose-700 hover:bg-rose-50"
          }`}
        >
          Mismatch
        </button>
        <button
          onClick={() => setFilterState("ready")}
          className={`px-2.5 py-1 rounded-lg transition-colors ${
            filterState === "ready" ? "bg-emerald-600 text-white" : "text-emerald-700 hover:bg-emerald-50"
          }`}
        >
          Ready
        </button>
      </div>

      {/* Case List Cards */}
      <div className="space-y-2.5 pt-1">
        {filteredDisputes.length === 0 ? (
          <div className="text-center py-8 text-xs text-slate-400">
            No dispute cases match your current filter.
          </div>
        ) : (
          filteredDisputes.map((d) => {
            const isSelected = d.dispute_id === selectedId;
            const meta = getHumanCaseMeta(d);

            return (
              <div
                key={d.dispute_id}
                onClick={() => onSelectCase(d.dispute_id)}
                className={`p-3.5 rounded-xl border text-left cursor-pointer transition-all duration-150 relative ${
                  isSelected
                    ? "border-blue-600 bg-blue-50/50 shadow-sm ring-1 ring-blue-600"
                    : "border-slate-200/80 hover:border-slate-300 bg-white hover:shadow-sm"
                }`}
              >
                {/* Product Name & Amount */}
                <div className="flex items-start justify-between gap-2 mb-1.5">
                  <h3 className="text-xs font-bold text-slate-900 leading-snug line-clamp-1">
                    {meta.productName}
                  </h3>
                  <span className="text-xs font-extrabold text-slate-900 shrink-0 font-mono">
                    ${d.amount.toFixed(2)}
                  </span>
                </div>

                {/* Status Badge */}
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border ${meta.statusClass}`}
                  >
                    {meta.statusIcon}
                    <span>{meta.statusLabel}</span>
                  </span>
                  <span className="text-[10px] text-slate-400 font-medium">
                    Buyer: {meta.buyerDisplayName}
                  </span>
                </div>

                {/* One-Line Plain English Explanation of What is Needed */}
                <p className="text-[11px] text-slate-600 bg-slate-50/80 p-2 rounded-lg border border-slate-100 line-clamp-2 leading-relaxed">
                  {meta.oneLineNeed}
                </p>

                {/* Footer with subtle ID */}
                <div className="mt-2 pt-1.5 flex items-center justify-between text-[10px] text-slate-400">
                  <span className="font-mono text-[9px] uppercase tracking-wider">
                    {d.dispute_id}
                  </span>
                  <span className="flex items-center gap-0.5 text-blue-600 font-semibold group-hover:underline">
                    <span>View case</span>
                    <ChevronRight className="w-3 h-3" />
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
