// ─── Approvals Tab Component ───

import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { format } from "date-fns";
import type { ApprovalTask } from "../types";

// ─── Types ───

interface ApprovalsTabProps {
  approvals: ApprovalTask[];
}

// ─── Horizontal Chain Timeline ───

function ChainTimeline({ approvals }: { approvals: ApprovalTask[] }) {
  const chainTotal = approvals.find((t) => t.chain_total !== null)?.chain_total ?? 0;
  if (chainTotal === 0) return null;
  if (!approvals.some((t) => t.chain_step !== null)) return null;

  const steps = Array.from({ length: chainTotal }, (_, i) => {
    const stepNum = i + 1;
    const stepTasks = approvals.filter((t) => t.chain_step === stepNum);
    const isCompleted = stepTasks.length > 0 && stepTasks.every(
      (t) => t.status === "approved" || t.status === "rejected"
    );
    const isPending = stepTasks.some((t) => t.status === "pending");
    const assignees = stepTasks.map((t) => t.assignee_name).join(", ");
    return { stepNum, isCompleted, isPending, assignees };
  });

  return (
    <Card className="mb-4">
      <CardContent className="pt-5 pb-4">
        <div className="flex items-start justify-center gap-0">
          {steps.map((step, idx) => (
            <React.Fragment key={step.stepNum}>
              {/* Step node */}
              <div className="flex flex-col items-center w-24">
                <div
                  className={`flex items-center justify-center w-9 h-9 rounded-full border-2 text-sm font-semibold ${
                    step.isCompleted
                      ? "border-green-500 bg-green-50 text-green-600"
                      : step.isPending
                      ? "border-yellow-400 bg-yellow-50 text-yellow-600"
                      : "border-gray-300 bg-white text-gray-400"
                  }`}
                >
                  {step.isCompleted ? (
                    <span>✓</span>
                  ) : step.isPending ? (
                    <span>⏳</span>
                  ) : (
                    <span>○</span>
                  )}
                </div>
                <p className="mt-1.5 text-xs font-medium text-gray-600 text-center">
                  Step {step.stepNum}
                </p>
                {step.assignees && (
                  <p className="text-xs text-gray-400 text-center leading-tight mt-0.5 max-w-full truncate">
                    {step.assignees}
                  </p>
                )}
              </div>
              {/* Connector */}
              {idx < steps.length - 1 && (
                <div
                  className={`flex-1 h-0.5 mt-4 mx-1 ${
                    steps[idx].isCompleted ? "bg-green-400" : "bg-gray-200"
                  }`}
                />
              )}
            </React.Fragment>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Vertical Stepper ───

function VerticalStepper({ approvals }: { approvals: ApprovalTask[] }) {
  const chainTotal = approvals.find((t) => t.chain_total !== null)?.chain_total ?? 0;

  if (chainTotal === 0 && approvals.length > 0) {
    // Non-chain approvals: show as single vertical step
    const sortedTasks = [...approvals].sort(
      (a, b) => new Date(a.assigned_at).getTime() - new Date(b.assigned_at).getTime()
    );
    return (
      <div className="space-y-3 mb-6">
        <h3 className="text-sm font-medium text-gray-700">
          Approval Steps ({sortedTasks.length} step{sortedTasks.length > 1 ? 's' : ''})
        </h3>
        {sortedTasks.map((task, idx) => (
          <div key={task.id} className="flex items-start gap-3">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0 ${
              task.status === 'approved' ? 'bg-green-500' :
              task.status === 'rejected' ? 'bg-red-500' :
              task.status === 'partially_approved' ? 'bg-blue-500' : 'bg-gray-300'
            }`}>{idx + 1}</div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{task.assignee_name}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full border ${
                  task.status === 'approved' ? 'border-green-300 text-green-700' :
                  task.status === 'rejected' ? 'border-red-300 text-red-700' :
                  task.status === 'partially_approved' ? 'border-blue-300 text-blue-700' :
                  'border-gray-300 text-gray-600'
                }`}>{task.status}</span>
              </div>
              <div className="text-xs text-gray-500 mt-0.5">Assigned: {format(new Date(task.assigned_at), "MMM d, yyyy")}</div>
              {task.decided_at && <div className="text-xs text-gray-500">Decided: {format(new Date(task.decided_at), "MMM d, yyyy")}</div>}
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (chainTotal === 0) return null;

  // Chain approvals: show by step
  const steps = Array.from({ length: chainTotal }, (_, i) => {
    const stepNum = i + 1;
    const stepTasks = approvals.filter((t) => t.chain_step === stepNum);
    const isCompleted = stepTasks.length > 0 && stepTasks.every(
      (t) => t.status === "approved" || t.status === "rejected"
    );
    const isPending = stepTasks.some((t) => t.status === "pending");
    const assignees = stepTasks.map((t) => t.assignee_name).join(", ");
    const statusMap: Record<string, boolean> = {};
    stepTasks.forEach((t) => {
      statusMap[t.status] = true;
    });
    const statuses = Object.keys(statusMap);
    const decidedAt = stepTasks.find((t) => t.decided_at)?.decided_at;
    return { stepNum, isCompleted, isPending, assignees, statuses, decidedAt };
  });

  return (
    <div className="space-y-3 mb-6">
      <h3 className="text-sm font-medium text-gray-700">
        Approval Chain ({chainTotal} step{chainTotal > 1 ? 's' : ''})
      </h3>
      {steps.map((step) => (
        <div key={step.stepNum} className="flex items-start gap-3">
          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0 ${
            step.isCompleted ? 'bg-green-500' :
            step.isPending ? 'bg-yellow-500' : 'bg-gray-300'
          }`}>{step.stepNum}</div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">Step {step.stepNum}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full border ${
                step.isCompleted ? 'border-green-300 text-green-700' :
                step.isPending ? 'border-yellow-300 text-yellow-700' :
                'border-gray-300 text-gray-600'
              }`}>{step.statuses.join(', ')}</span>
            </div>
            {step.assignees && <div className="text-xs text-gray-600 mt-0.5">Assignee(s): {step.assignees}</div>}
            {step.decidedAt && <div className="text-xs text-gray-500">Decided: {format(new Date(step.decidedAt), "MMM d, yyyy")}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Main Component ───

export function ApprovalsTab({ approvals }: ApprovalsTabProps) {
  return (
    <>
      <ChainTimeline approvals={approvals} />
      <VerticalStepper approvals={approvals} />

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Assignee</TableHead>
                <TableHead>Step</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Assigned At</TableHead>
                <TableHead>Decided At</TableHead>
                <TableHead>Notes</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {approvals.map((task) => (
                <TableRow key={task.id}>
                  <TableCell>{task.assignee_name}</TableCell>
                  <TableCell className="text-sm text-gray-500">
                    {task.chain_step && task.chain_total
                      ? `${task.chain_step}/${task.chain_total}`
                      : "—"}
                  </TableCell>
                  <TableCell>
                    <Badge>{task.status}</Badge>
                  </TableCell>
                  <TableCell className="text-sm text-gray-500">
                    {format(new Date(task.assigned_at), "MMM d, yyyy")}
                  </TableCell>
                  <TableCell className="text-sm text-gray-500">
                    {task.decided_at ? format(new Date(task.decided_at), "MMM d, yyyy") : "—"}
                  </TableCell>
                  <TableCell>{task.notes || "—"}</TableCell>
                </TableRow>
              ))}
              {approvals.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-gray-400 py-6">
                    No approval tasks.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </>
  );
}
