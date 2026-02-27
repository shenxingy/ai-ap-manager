"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import api from "@/lib/api";

// ─── Types ───

interface FraudIncident {
  id: string;
  invoice_id: string;
  score_at_flag: number;
  triggered_signals: string[];
  reviewed_by: string | null;
  outcome: string;
  notes: string | null;
  created_at: string;
}

// ─── Helpers ───

function extractApiError(err: unknown): string {
  return (
    (err as { response?: { data?: { detail?: string } } })?.response?.data
      ?.detail ?? "Operation failed"
  );
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// ─── Toast ───

interface ToastState {
  message: string;
  type: "success" | "error";
}

function useToast() {
  const [toast, setToast] = useState<ToastState | null>(null);
  const showToast = (message: string, type: "success" | "error") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };
  return { toast, showToast };
}

function ToastBanner({ toast }: { toast: ToastState | null }) {
  if (!toast) return null;
  return (
    <div
      className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white ${
        toast.type === "success" ? "bg-green-600" : "bg-red-600"
      }`}
    >
      {toast.message}
    </div>
  );
}

// ─── Score Badge ───

function ScoreBadge({ score }: { score: number }) {
  let cls = "bg-yellow-100 text-yellow-700";
  if (score >= 60) cls = "bg-red-100 text-red-700";
  else if (score >= 40) cls = "bg-orange-100 text-orange-700";

  return (
    <span
      className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold tabular-nums ${cls}`}
    >
      {score}
    </span>
  );
}

// ─── Outcome Badge ───

function OutcomeBadge({ outcome }: { outcome: string }) {
  const map: Record<string, string> = {
    pending: "bg-yellow-100 text-yellow-700",
    genuine: "bg-green-100 text-green-700",
    false_positive: "bg-gray-100 text-gray-500",
  };
  const label: Record<string, string> = {
    pending: "Pending",
    genuine: "Genuine",
    false_positive: "False Positive",
  };
  const cls = map[outcome] ?? "bg-gray-100 text-gray-500";
  return (
    <span
      className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${cls}`}
    >
      {label[outcome] ?? outcome}
    </span>
  );
}

// ─── Detail Sheet ───

interface DetailSheetProps {
  incident: FraudIncident | null;
  onClose: () => void;
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}

function DetailSheet({
  incident,
  onClose,
  onSuccess,
  onError,
}: DetailSheetProps) {
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState(incident?.notes ?? "");
  const [outcome, setOutcome] = useState(incident?.outcome ?? "pending");

  // State is initialized from incident props; re-mounting on selection change handles sync

  const mutation = useMutation({
    mutationFn: async () => {
      const res = await api.patch<FraudIncident>(
        `/fraud-incidents/${incident!.id}`,
        { outcome, notes: notes.trim() || null }
      );
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["fraud-incidents"] });
      onSuccess("Incident updated");
      onClose();
    },
    onError: (err) => onError(extractApiError(err)),
  });

  if (!incident) return null;

  return (
    <Sheet open={incident !== null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-[480px] sm:w-[540px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Fraud Incident Review</SheetTitle>
        </SheetHeader>

        <div className="mt-6 space-y-5">
          {/* Score */}
          <div className="flex items-center gap-4 p-4 rounded-lg bg-gray-50">
            <div className="text-center">
              <div className="text-3xl font-bold tabular-nums">
                <ScoreBadge score={incident.score_at_flag} />
              </div>
              <div className="text-xs text-gray-500 mt-1">Fraud Score</div>
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-700 mb-1">
                Triggered Signals
              </p>
              <div className="flex flex-wrap gap-1.5">
                {incident.triggered_signals.length > 0 ? (
                  incident.triggered_signals.map((sig) => (
                    <span
                      key={sig}
                      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono bg-red-50 text-red-700"
                    >
                      {sig}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-gray-400">None</span>
                )}
              </div>
            </div>
          </div>

          {/* Invoice link */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1">
              Invoice
            </p>
            <Link
              href={`/invoices/${incident.invoice_id}`}
              className="text-sm text-blue-600 hover:underline font-mono"
            >
              {incident.invoice_id.slice(0, 8)}…
            </Link>
          </div>

          {/* Detected at */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1">
              Flagged On
            </p>
            <p className="text-sm text-gray-700">{fmtDate(incident.created_at)}</p>
          </div>

          {/* Outcome selector */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">
              Outcome
            </p>
            <Select value={outcome} onValueChange={setOutcome}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="pending">Pending</SelectItem>
                <SelectItem value="genuine">Genuine Fraud</SelectItem>
                <SelectItem value="false_positive">False Positive</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Notes */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">
              Notes
            </p>
            <textarea
              className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
              rows={4}
              placeholder="Add investigation notes…"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          {/* Actions */}
          <div className="flex gap-2 pt-2">
            <Button
              className="flex-1"
              disabled={mutation.isPending}
              onClick={() => mutation.mutate()}
            >
              {mutation.isPending ? "Saving…" : "Mark Reviewed"}
            </Button>
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

// ─── Tabs ───

type OutcomeFilter = "all" | "pending" | "genuine" | "false_positive";

const TABS: { value: OutcomeFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "genuine", label: "Genuine" },
  { value: "false_positive", label: "False Positive" },
];

// ─── Page ───

export default function AdminFraudPage() {
  const [filter, setFilter] = useState<OutcomeFilter>("all");
  const [selectedIncident, setSelectedIncident] =
    useState<FraudIncident | null>(null);
  const { toast, showToast } = useToast();

  const { data: incidents, isLoading } = useQuery<FraudIncident[]>({
    queryKey: ["fraud-incidents", filter],
    queryFn: () =>
      api
        .get<FraudIncident[]>("/fraud-incidents", {
          params: filter !== "all" ? { outcome: filter } : {},
        })
        .then((r) => r.data),
  });

  return (
    <div className="space-y-4">
      <ToastBanner toast={toast} />

      <div>
        <h2 className="text-2xl font-bold text-gray-900">Fraud Incidents</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Invoices flagged by the fraud scoring engine
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setFilter(tab.value)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              filter === tab.value
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Invoice ID</TableHead>
                <TableHead>Score</TableHead>
                <TableHead>Signals</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead>Flagged On</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow>
                  <TableCell
                    colSpan={5}
                    className="text-center text-gray-400 py-8"
                  >
                    Loading…
                  </TableCell>
                </TableRow>
              )}
              {!isLoading && (!incidents || incidents.length === 0) && (
                <TableRow>
                  <TableCell
                    colSpan={5}
                    className="text-center text-gray-400 py-8"
                  >
                    No fraud incidents found
                    {filter !== "all" ? ` with outcome "${filter}"` : ""}.
                  </TableCell>
                </TableRow>
              )}
              {incidents?.map((incident) => (
                <TableRow
                  key={incident.id}
                  className="cursor-pointer hover:bg-gray-50"
                  onClick={() => setSelectedIncident(incident)}
                >
                  <TableCell className="font-mono text-xs text-gray-600">
                    {incident.invoice_id.slice(0, 8)}…
                  </TableCell>
                  <TableCell>
                    <ScoreBadge score={incident.score_at_flag} />
                  </TableCell>
                  <TableCell className="text-sm text-gray-600 max-w-xs truncate">
                    {incident.triggered_signals.length > 0
                      ? incident.triggered_signals.join(", ")
                      : <span className="text-gray-300">—</span>}
                  </TableCell>
                  <TableCell>
                    <OutcomeBadge outcome={incident.outcome} />
                  </TableCell>
                  <TableCell className="text-sm text-gray-500">
                    {fmtDate(incident.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <DetailSheet
        incident={selectedIncident}
        onClose={() => setSelectedIncident(null)}
        onSuccess={(msg) => showToast(msg, "success")}
        onError={(msg) => showToast(msg, "error")}
      />
    </div>
  );
}
