"use client";

import React from "react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import api from "@/lib/api";

// ─── Helper Components ───

export function ConfidenceDot({ score }: { score: number | null | undefined }) {
  if (score == null)
    return <span className="inline-block w-2 h-2 rounded-full bg-gray-300 ml-1.5" title="No confidence data" />;
  if (score >= 0.9)
    return <span className="inline-block w-2 h-2 rounded-full bg-green-500 ml-1.5" title={`${(score * 100).toFixed(0)}% confidence`} />;
  if (score >= 0.6)
    return <span className="inline-block w-2 h-2 rounded-full bg-yellow-400 ml-1.5" title={`${(score * 100).toFixed(0)}% confidence`} />;
  return <span className="inline-block w-2 h-2 rounded-full bg-red-500 ml-1.5" title={`${(score * 100).toFixed(0)}% confidence`} />;
}

export function GlConfBadge({ score }: { score: number | null | undefined }) {
  if (score == null) return null;
  const pct = `${(score * 100).toFixed(0)}%`;
  if (score >= 0.9) return <span className="text-xs bg-green-100 text-green-700 px-1 py-0.5 rounded">{pct}</span>;
  if (score >= 0.6) return <span className="text-xs bg-yellow-100 text-yellow-700 px-1 py-0.5 rounded">{pct}</span>;
  return <span className="text-xs bg-red-100 text-red-700 px-1 py-0.5 rounded">{pct}</span>;
}

// ─── Fraud Badge ───

export function fraudBadge(score: number | null): string {
  if (score === null) return "N/A";
  if (score >= 0.9) return "🔴🔴 CRITICAL";
  if (score >= 0.7) return "🔴 HIGH";
  if (score >= 0.4) return "🟡 MEDIUM";
  return "🟢 LOW";
}

// ─── Match Helpers ───

export function matchLineClass(status: string): string {
  if (status === "matched" || status === "MATCHED")
    return "border-l-4 border-l-green-500 bg-green-50/50";
  if (status === "qty_variance" || status === "price_variance" || status === "WITHIN_TOLERANCE")
    return "border-l-4 border-l-yellow-400 bg-yellow-50/50";
  if (status === "unmatched" || status === "OUT_OF_TOLERANCE")
    return "border-l-4 border-l-red-500 bg-red-50/50";
  return "";
}

export function matchStatusLabel(status: string): string {
  if (status === "matched") return "Matched";
  if (status === "qty_variance") return "Qty Variance";
  if (status === "price_variance") return "Price Variance";
  if (status === "unmatched") return "Unmatched";
  return status;
}

export function matchStatusClass(status: string): string {
  if (status === "matched") return "text-green-600 font-medium text-xs";
  if (status === "qty_variance" || status === "price_variance") return "text-yellow-600 font-medium text-xs";
  return "text-red-600 font-medium text-xs";
}

export function matchTypeBadge(matchType: string): { label: string; cls: string } {
  if (matchType === "3way") return { label: "3-Way Match", cls: "bg-purple-100 text-purple-700 border border-purple-200" };
  if (matchType === "2way") return { label: "2-Way Match", cls: "bg-blue-100 text-blue-700 border border-blue-200" };
  return { label: "Non-PO", cls: "bg-gray-100 text-gray-600 border border-gray-200" };
}

export function InspectionBadge({ status }: { status: string | null | undefined }) {
  const s = (status ?? "").toUpperCase();
  if (s === "PASS" || s === "PASSED")
    return <span className="inline-flex items-center gap-1 text-xs font-medium text-green-700 bg-green-100 px-2 py-0.5 rounded-full">✓ Pass</span>;
  if (s === "FAIL" || s === "FAILED")
    return <span className="inline-flex items-center gap-1 text-xs font-medium text-red-700 bg-red-100 px-2 py-0.5 rounded-full">✗ Fail</span>;
  if (s === "PARTIAL")
    return <span className="inline-flex items-center gap-1 text-xs font-medium text-yellow-700 bg-yellow-100 px-2 py-0.5 rounded-full">⚠ Partial</span>;
  return <span className="inline-flex items-center gap-1 text-xs font-medium text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full">— Pending</span>;
}

// ─── Record Payment Dialog ───

export function RecordPaymentDialog({
  invoiceId,
  onSuccess,
}: {
  invoiceId: string;
  onSuccess: () => void;
}) {
  const [open, setOpen] = React.useState(false);
  const [method, setMethod] = React.useState("ACH");
  const [reference, setReference] = React.useState("");
  const [loading, setLoading] = React.useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    try {
      await api.post(`/invoices/${invoiceId}/payment`, {
        payment_method: method,
        payment_reference: reference || null,
      });
      setOpen(false);
      onSuccess();
    } catch {
      // Error is shown via existing error boundary
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" className="border-green-300 text-green-700 hover:bg-green-50">
          Record Payment
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Record Payment</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1">
            <Label>Payment Method</Label>
            <Select value={method} onValueChange={setMethod}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ACH">ACH</SelectItem>
                <SelectItem value="Wire">Wire Transfer</SelectItem>
                <SelectItem value="Check">Check</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Reference / Trace Number (optional)</Label>
            <Input
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              placeholder="ACH trace number or check #"
            />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={handleSubmit} disabled={loading}>
            {loading ? "Recording..." : "Confirm Payment"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
