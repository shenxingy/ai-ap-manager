"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { format } from "date-fns";
import api from "@/lib/api";
import Link from "next/link";

// ─── Types ───

interface ApprovalTask {
  id: string;
  invoice_id: string;
  invoice_number: string | null;
  vendor_name: string | null;
  vendor_name_raw: string | null;
  total_amount: number | null;
  status: string;
  approval_required_count?: number;
  assigned_at: string;
  created_at: string;
  decided_at: string | null;
  notes: string | null;
}

interface ApprovalListResponse {
  items: ApprovalTask[];
  total: number;
}

interface MatchResult {
  id: string;
  invoice_id: string;
  match_type: string;
  match_status: string;
  amount_variance_pct: number | null;
  po_number: string | null;
  gr_number: string | null;
  line_matches: Array<{ status: string }>;
}

type DecisionType = "approve" | "reject";
type TabType = "pending" | "past";

// ─── Decision Modal ───

function DecisionModal({
  task,
  decision,
  onClose,
  onSuccess,
}: {
  task: ApprovalTask | null;
  decision: DecisionType | null;
  onClose: () => void;
  onSuccess: (action: string) => void;
}) {
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const { data: matchResult } = useQuery<MatchResult>({
    queryKey: ["match", task?.invoice_id],
    queryFn: () =>
      api.get(`/invoices/${task!.invoice_id}/match`).then((r) => r.data),
    enabled: !!task,
  });

  const submit = useMutation({
    mutationFn: () =>
      api.post(`/approvals/${task!.id}/${decision}`, { notes }),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      const result = response.data;
      let action: string;
      if (result?.status === "partially_approved") {
        action = "First approval recorded — awaiting 2nd admin approval";
      } else {
        action = decision === "approve" ? "Invoice approved" : "Invoice rejected";
      }
      onSuccess(action);
      setNotes("");
      setSubmitError(null);
      onClose();
    },
    onError: (error: unknown) => {
      const msg =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? "An unexpected error occurred. Please try again.";
      setSubmitError(msg);
    },
  });

  const isOpen = !!task && !!decision;
  const canSubmit = decision === "approve" || (decision === "reject" && notes.trim());

  const getStatusColor = (status: string) => {
    if (status === "matched") return "bg-green-100 text-green-800";
    if (status === "partial") return "bg-amber-100 text-amber-800";
    if (status === "exception") return "bg-red-100 text-red-800";
    return "bg-gray-100 text-gray-800";
  };

  const handleSubmit = () => {
    const confirmMsg =
      task?.status === "partially_approved" && decision === "approve"
        ? "Add your 2nd approval for this invoice? This will complete dual-auth."
        : decision === "approve"
        ? "Are you sure you want to approve this invoice?"
        : "Are you sure you want to reject this invoice? This action cannot be undone.";

    if (window.confirm(confirmMsg)) {
      submit.mutate();
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) { setSubmitError(null); onClose(); } }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {decision === "approve"
              ? task?.status === "partially_approved"
                ? "Add 2nd Approval"
                : "Approve Invoice"
              : "Reject Invoice"}
          </DialogTitle>
        </DialogHeader>
        {task && (
          <div className="space-y-4">
            {/* Dual-auth progress indicator */}
            {task.status === "partially_approved" && decision === "approve" && (
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm">
                <p className="font-semibold text-yellow-800 mb-1">CRITICAL — Dual Auth Required</p>
                <div className="flex items-center gap-3 text-yellow-700">
                  <span className="flex items-center gap-1">
                    <span className="text-base">◉</span> 1st approval given
                  </span>
                  <span>→</span>
                  <span className="flex items-center gap-1">
                    <span className="text-base">◎</span> 2nd approval needed
                  </span>
                </div>
              </div>
            )}
            <div className="bg-gray-50 rounded-lg p-3 text-sm">
              <p className="font-medium">Invoice {task.invoice_number || task.invoice_id.slice(0, 8)}</p>
              <p className="text-gray-500">{task.vendor_name_raw || task.vendor_name}</p>
              {task.total_amount && (
                <p className="text-gray-700 mt-1">
                  ${task.total_amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </p>
              )}
            </div>

            {/* Match Result Summary */}
            {matchResult ? (
              <div className="bg-blue-50 rounded-lg p-3 text-sm border border-blue-100">
                <p className="font-medium text-blue-900 mb-2">Match Summary</p>
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-gray-600">Type:</span>
                    <Badge className="bg-blue-600">
                      {matchResult.match_type === "2way" ? "2-Way" : matchResult.match_type === "3way" ? "3-Way" : matchResult.match_type}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-gray-600">Status:</span>
                    <Badge className={getStatusColor(matchResult.match_status)}>
                      {matchResult.match_status.charAt(0).toUpperCase() + matchResult.match_status.slice(1)}
                    </Badge>
                  </div>
                  {matchResult.amount_variance_pct !== null && (
                    <div className="flex items-center gap-2">
                      <span className="text-gray-600">Variance:</span>
                      <span className="text-gray-800">
                        {matchResult.amount_variance_pct > 0 ? "+" : ""}{matchResult.amount_variance_pct.toFixed(2)}%
                      </span>
                    </div>
                  )}
                  {matchResult.po_number && (
                    <div className="text-xs text-gray-600">
                      PO: {matchResult.po_number}
                    </div>
                  )}
                  {matchResult.gr_number && (
                    <div className="text-xs text-gray-600">
                      GR: {matchResult.gr_number}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-600">
                Match data unavailable
              </div>
            )}
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-1">
                Notes {decision === "reject" && <span className="text-red-500">*</span>}
              </label>
              <textarea
                className="w-full border rounded-md px-3 py-2 text-sm resize-none"
                rows={3}
                placeholder={decision === "approve" ? "Optional notes..." : "Reason for rejection..."}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>
            {submitError && (
              <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                {submitError}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={onClose} disabled={submit.isPending}>
                Cancel
              </Button>
              <Button
                variant={decision === "approve" ? "default" : "destructive"}
                disabled={!canSubmit || submit.isPending}
                onClick={handleSubmit}
              >
                {submit.isPending
                ? "Submitting..."
                : decision === "approve"
                ? task?.status === "partially_approved"
                  ? "Add 2nd Approval"
                  : "Approve"
                : "Reject"}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ─── Past Decisions Table ───

function PastDecisionsTable({ tasks }: { tasks: ApprovalTask[] }) {
  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Invoice</TableHead>
              <TableHead>Vendor</TableHead>
              <TableHead className="text-right">Amount</TableHead>
              <TableHead>Decision</TableHead>
              <TableHead>Decided At</TableHead>
              <TableHead>Notes</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tasks.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-gray-400 py-8">
                  No past decisions yet.
                </TableCell>
              </TableRow>
            )}
            {tasks.map((task) => (
              <TableRow key={task.id}>
                <TableCell>
                  <Link
                    href={`/invoices/${task.invoice_id}`}
                    className="text-blue-600 hover:underline font-medium"
                  >
                    {task.invoice_number || task.invoice_id.slice(0, 8)}
                  </Link>
                </TableCell>
                <TableCell>{task.vendor_name_raw || task.vendor_name || "—"}</TableCell>
                <TableCell className="text-right">
                  {task.total_amount != null
                    ? `$${task.total_amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                    : "—"}
                </TableCell>
                <TableCell>
                  <Badge
                    variant={task.status === "approved" ? "default" : "destructive"}
                    className={task.status === "approved" ? "bg-green-100 text-green-800 hover:bg-green-100" : ""}
                  >
                    {task.status === "approved" ? "Approved" : "Rejected"}
                  </Badge>
                </TableCell>
                <TableCell className="text-sm text-gray-500">
                  {task.decided_at
                    ? format(new Date(task.decided_at), "MMM d, yyyy")
                    : "—"}
                </TableCell>
                <TableCell className="text-sm text-gray-500 max-w-xs truncate">
                  {task.notes || "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// ─── Page ───

export default function ApprovalsPage() {
  const [activeTab, setActiveTab] = useState<TabType>("pending");
  const [selectedTask, setSelectedTask] = useState<ApprovalTask | null>(null);
  const [decision, setDecision] = useState<DecisionType | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const { data: pendingData } = useQuery<ApprovalListResponse>({
    queryKey: ["approvals", "pending"],
    queryFn: () => api.get("/approvals").then((r) => r.data),
  });

  const { data: resolvedData } = useQuery<ApprovalListResponse>({
    queryKey: ["approvals", "resolved"],
    queryFn: () => api.get("/approvals?include_resolved=true").then((r) => r.data),
    enabled: activeTab === "past",
  });

  const tasks = pendingData?.items ?? [];
  const resolvedTasks = resolvedData?.items ?? [];

  const openDecision = (task: ApprovalTask, d: DecisionType) => {
    setSelectedTask(task);
    setDecision(d);
  };

  const closeModal = () => {
    setSelectedTask(null);
    setDecision(null);
  };

  const showSuccess = (message: string) => {
    setToast(message);
    setTimeout(() => setToast(null), 3500);
  };

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold text-gray-900">Approvals</h2>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        <button
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "pending"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
          onClick={() => setActiveTab("pending")}
        >
          Pending
          {tasks.length > 0 && (
            <span className="ml-2 inline-flex items-center justify-center rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800">
              {tasks.length}
            </span>
          )}
        </button>
        <button
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "past"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
          onClick={() => setActiveTab("past")}
        >
          Past Decisions
        </button>
      </div>

      {/* Pending Tab */}
      {activeTab === "pending" && (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Invoice</TableHead>
                  <TableHead>Vendor</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Assigned At</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tasks.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-gray-400 py-8">
                      No pending approvals.
                    </TableCell>
                  </TableRow>
                )}
                {tasks.map((task) => (
                  <TableRow key={task.id}>
                    <TableCell>
                      <Link
                        href={`/invoices/${task.invoice_id}`}
                        className="text-blue-600 hover:underline font-medium"
                      >
                        {task.invoice_number || task.invoice_id.slice(0, 8)}
                      </Link>
                    </TableCell>
                    <TableCell>{task.vendor_name_raw || task.vendor_name || "—"}</TableCell>
                    <TableCell className="text-right">
                      {task.total_amount != null
                        ? `$${task.total_amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                        : "—"}
                    </TableCell>
                    <TableCell>
                      {task.status === "partially_approved" ? (
                        <div className="flex flex-col gap-1">
                          <Badge className="bg-yellow-100 text-yellow-800 border border-yellow-200 hover:bg-yellow-100 w-fit">
                            1 of {task.approval_required_count ?? 2} approvals
                          </Badge>
                          <span className="text-xs text-yellow-700 font-medium">
                            ◉ 1 / ◎ {task.approval_required_count ?? 2}
                          </span>
                        </div>
                      ) : (
                        <Badge variant="outline">{task.status}</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-gray-500">
                      {format(new Date(task.created_at || task.assigned_at), "MMM d, yyyy")}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          onClick={() => openDecision(task, "approve")}
                        >
                          {task.status === "partially_approved" ? "Add 2nd Approval" : "Approve"}
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => openDecision(task, "reject")}
                        >
                          Reject
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Past Decisions Tab */}
      {activeTab === "past" && <PastDecisionsTable tasks={resolvedTasks} />}

      <DecisionModal task={selectedTask} decision={decision} onClose={closeModal} onSuccess={showSuccess} />

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-4 right-4 z-50 px-4 py-2.5 rounded-lg shadow-lg text-sm font-medium text-white bg-green-600 transition-opacity">
          {toast}
        </div>
      )}
    </div>
  );
}
