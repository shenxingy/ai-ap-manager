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
  total_amount: number | null;
  status: string;
  assigned_at: string;
}

type DecisionType = "approve" | "reject";

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

  const submit = useMutation({
    mutationFn: () =>
      api.post(`/approvals/${task!.id}/${decision}`, { notes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      const action = decision === "approve" ? "Invoice approved" : "Invoice rejected";
      onSuccess(action);
      setNotes("");
      onClose();
    },
  });

  const isOpen = !!task && !!decision;
  const canSubmit = decision === "approve" || (decision === "reject" && notes.trim());

  const handleSubmit = () => {
    const confirmMsg =
      decision === "approve"
        ? "Are you sure you want to approve this invoice?"
        : "Are you sure you want to reject this invoice? This action cannot be undone.";

    if (window.confirm(confirmMsg)) {
      submit.mutate();
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {decision === "approve" ? "Approve Invoice" : "Reject Invoice"}
          </DialogTitle>
        </DialogHeader>
        {task && (
          <div className="space-y-4">
            <div className="bg-gray-50 rounded-lg p-3 text-sm">
              <p className="font-medium">Invoice {task.invoice_number || task.invoice_id.slice(0, 8)}</p>
              <p className="text-gray-500">{task.vendor_name}</p>
              {task.total_amount && (
                <p className="text-gray-700 mt-1">
                  ${task.total_amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </p>
              )}
            </div>
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
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={onClose} disabled={submit.isPending}>
                Cancel
              </Button>
              <Button
                variant={decision === "approve" ? "default" : "destructive"}
                disabled={!canSubmit || submit.isPending}
                onClick={handleSubmit}
              >
                {submit.isPending ? "Submitting..." : decision === "approve" ? "Approve" : "Reject"}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ─── Page ───

export default function ApprovalsPage() {
  const [selectedTask, setSelectedTask] = useState<ApprovalTask | null>(null);
  const [decision, setDecision] = useState<DecisionType | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const { data: tasks = [] } = useQuery<ApprovalTask[]>({
    queryKey: ["approvals"],
    queryFn: () => api.get("/approvals").then((r) => r.data),
  });

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
      <h2 className="text-2xl font-bold text-gray-900">Pending Approvals</h2>

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
                  <TableCell>{task.vendor_name || "—"}</TableCell>
                  <TableCell className="text-right">
                    {task.total_amount != null
                      ? `$${task.total_amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                      : "—"}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{task.status}</Badge>
                  </TableCell>
                  <TableCell className="text-sm text-gray-500">
                    {format(new Date(task.assigned_at), "MMM d, yyyy")}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={() => openDecision(task, "approve")}
                      >
                        Approve
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
