"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import api from "@/lib/api";

// ─── Types ───

interface ApprovalMatrixRule {
  id: string;
  amount_min: number | null;
  amount_max: number | null;
  department: string | null;
  category: string | null;
  approver_role: string;
  step_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// ─── Constants ───

const APPROVER_ROLES = ["AP_CLERK", "AP_ANALYST", "APPROVER", "ADMIN"];

// ─── Helpers ───

function extractApiError(err: unknown): string {
  return (
    (err as { response?: { data?: { detail?: string } } })?.response?.data
      ?.detail ?? "Operation failed"
  );
}

function fmtAmount(val: number | null): string {
  if (val == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(val);
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

// ─── Status Badge ───

function StatusBadge({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
        active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"
      }`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${active ? "bg-green-500" : "bg-gray-400"}`}
      />
      {active ? "Active" : "Inactive"}
    </span>
  );
}

// ─── Rule Form ───

interface RuleFormState {
  amount_min: string;
  amount_max: string;
  department: string;
  category: string;
  approver_role: string;
  step_order: string;
  is_active: boolean;
}

const EMPTY_FORM: RuleFormState = {
  amount_min: "",
  amount_max: "",
  department: "",
  category: "",
  approver_role: "APPROVER",
  step_order: "1",
  is_active: true,
};

function ruleToForm(rule: ApprovalMatrixRule): RuleFormState {
  return {
    amount_min: rule.amount_min != null ? String(rule.amount_min) : "",
    amount_max: rule.amount_max != null ? String(rule.amount_max) : "",
    department: rule.department ?? "",
    category: rule.category ?? "",
    approver_role: rule.approver_role,
    step_order: String(rule.step_order),
    is_active: rule.is_active,
  };
}

function formToPayload(form: RuleFormState) {
  return {
    amount_min: form.amount_min ? parseFloat(form.amount_min) : null,
    amount_max: form.amount_max ? parseFloat(form.amount_max) : null,
    department: form.department.trim() || null,
    category: form.category.trim() || null,
    approver_role: form.approver_role,
    step_order: parseInt(form.step_order, 10) || 1,
    is_active: form.is_active,
  };
}

// ─── Rule Dialog ───

interface RuleDialogProps {
  open: boolean;
  editRule: ApprovalMatrixRule | null;
  onClose: () => void;
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}

function RuleDialog({
  open,
  editRule,
  onClose,
  onSuccess,
  onError,
}: RuleDialogProps) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<RuleFormState>(EMPTY_FORM);

  useEffect(() => {
    setForm(editRule ? ruleToForm(editRule) : EMPTY_FORM);
  }, [open, editRule?.id]);

  const mutation = useMutation({
    mutationFn: async () => {
      const payload = formToPayload(form);
      if (editRule) {
        const res = await api.put<ApprovalMatrixRule>(
          `/approval-matrix/${editRule.id}`,
          payload
        );
        return res.data;
      } else {
        const res = await api.post<ApprovalMatrixRule>(
          "/approval-matrix",
          payload
        );
        return res.data;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["approval-matrix"] });
      onSuccess(editRule ? "Rule updated" : "Rule created");
      onClose();
    },
    onError: (err) => onError(extractApiError(err)),
  });

  const isValid = form.approver_role.length > 0;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {editRule ? "Edit Approval Rule" : "New Approval Rule"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="amt-min">Min Amount ($)</Label>
              <Input
                id="amt-min"
                type="number"
                min={0}
                placeholder="e.g. 0"
                value={form.amount_min}
                onChange={(e) =>
                  setForm({ ...form, amount_min: e.target.value })
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="amt-max">Max Amount ($)</Label>
              <Input
                id="amt-max"
                type="number"
                min={0}
                placeholder="e.g. 10000"
                value={form.amount_max}
                onChange={(e) =>
                  setForm({ ...form, amount_max: e.target.value })
                }
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="dept">Department</Label>
              <Input
                id="dept"
                placeholder="e.g. Finance"
                value={form.department}
                onChange={(e) =>
                  setForm({ ...form, department: e.target.value })
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cat">Category</Label>
              <Input
                id="cat"
                placeholder="e.g. Software"
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>
                Approver Role <span className="text-red-500">*</span>
              </Label>
              <Select
                value={form.approver_role}
                onValueChange={(v) => setForm({ ...form, approver_role: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {APPROVER_ROLES.map((role) => (
                    <SelectItem key={role} value={role}>
                      {role}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="step">Step Order</Label>
              <Input
                id="step"
                type="number"
                min={1}
                value={form.step_order}
                onChange={(e) =>
                  setForm({ ...form, step_order: e.target.value })
                }
              />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!isValid || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending
              ? editRule
                ? "Saving…"
                : "Creating…"
              : editRule
                ? "Save Changes"
                : "Create Rule"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Confirm Delete Dialog ───

interface ConfirmDeleteDialogProps {
  rule: ApprovalMatrixRule | null;
  onClose: () => void;
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}

function ConfirmDeleteDialog({
  rule,
  onClose,
  onSuccess,
  onError,
}: ConfirmDeleteDialogProps) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: async () => {
      await api.delete(`/approval-matrix/${rule!.id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["approval-matrix"] });
      onSuccess("Rule deleted");
      onClose();
    },
    onError: (err) => onError(extractApiError(err)),
  });

  return (
    <Dialog open={rule !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete Approval Rule</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-gray-600 py-2">
          Are you sure you want to delete this rule? This action cannot be
          undone.
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Deleting…" : "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Preview Card ───

function ApprovalPreview({ rules }: { rules: ApprovalMatrixRule[] }) {
  const [amount, setAmount] = useState("5000");
  const [dept, setDept] = useState("");

  const numAmount = parseFloat(amount) || 0;

  const steps = rules
    .filter((r) => {
      if (!r.is_active) return false;
      if (r.amount_min != null && numAmount < r.amount_min) return false;
      if (r.amount_max != null && numAmount > r.amount_max) return false;
      if (r.department && dept && r.department !== dept) return false;
      return true;
    })
    .sort((a, b) => a.step_order - b.step_order);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold text-gray-700">
          Approval Flow Preview
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-3 mb-4">
          <div className="flex-1">
            <Label htmlFor="prev-amount" className="text-xs">
              Invoice Amount ($)
            </Label>
            <Input
              id="prev-amount"
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="mt-1 h-8 text-sm"
            />
          </div>
          <div className="flex-1">
            <Label htmlFor="prev-dept" className="text-xs">
              Department (optional)
            </Label>
            <Input
              id="prev-dept"
              placeholder="e.g. Finance"
              value={dept}
              onChange={(e) => setDept(e.target.value)}
              className="mt-1 h-8 text-sm"
            />
          </div>
        </div>
        {steps.length === 0 ? (
          <p className="text-sm text-gray-400 italic">
            No matching rules — invoice may auto-approve.
          </p>
        ) : (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-gray-500">Invoice</span>
            {steps.map((step) => (
              <span key={step.id} className="flex items-center gap-2">
                <span className="text-gray-400">→</span>
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700">
                  Step {step.step_order}: {step.approver_role}
                </span>
              </span>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Page ───

export default function AdminApprovalMatrixPage() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editRule, setEditRule] = useState<ApprovalMatrixRule | null>(null);
  const [deleteRule, setDeleteRule] = useState<ApprovalMatrixRule | null>(null);
  const { toast, showToast } = useToast();

  const { data: rules, isLoading } = useQuery<ApprovalMatrixRule[]>({
    queryKey: ["approval-matrix"],
    queryFn: () =>
      api.get<ApprovalMatrixRule[]>("/approval-matrix").then((r) => r.data),
  });

  const handleEdit = (rule: ApprovalMatrixRule) => {
    setEditRule(rule);
    setDialogOpen(true);
  };

  const handleAdd = () => {
    setEditRule(null);
    setDialogOpen(true);
  };

  const handleDialogClose = () => {
    setDialogOpen(false);
    setEditRule(null);
  };

  return (
    <div className="space-y-4">
      <ToastBanner toast={toast} />

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Approval Matrix</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Define multi-step approval rules by amount, department, and category
          </p>
        </div>
        <Button onClick={handleAdd}>Add Rule</Button>
      </div>

      {rules && rules.length > 0 && <ApprovalPreview rules={rules} />}

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Amount Band</TableHead>
                <TableHead>Department</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Approver Role</TableHead>
                <TableHead>Step</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-20">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow>
                  <TableCell
                    colSpan={7}
                    className="text-center text-gray-400 py-8"
                  >
                    Loading…
                  </TableCell>
                </TableRow>
              )}
              {!isLoading && (!rules || rules.length === 0) && (
                <TableRow>
                  <TableCell
                    colSpan={7}
                    className="text-center text-gray-400 py-8"
                  >
                    No rules yet. Click Add Rule to create one.
                  </TableCell>
                </TableRow>
              )}
              {rules?.map((rule) => (
                <TableRow key={rule.id}>
                  <TableCell className="font-mono text-sm">
                    {fmtAmount(rule.amount_min)} –{" "}
                    {rule.amount_max != null ? fmtAmount(rule.amount_max) : "∞"}
                  </TableCell>
                  <TableCell className="text-sm text-gray-600">
                    {rule.department ?? <span className="text-gray-300">Any</span>}
                  </TableCell>
                  <TableCell className="text-sm text-gray-600">
                    {rule.category ?? <span className="text-gray-300">Any</span>}
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-700">
                      {rule.approver_role}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-gray-600">
                    {rule.step_order}
                  </TableCell>
                  <TableCell>
                    <StatusBadge active={rule.is_active} />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0"
                        onClick={() => handleEdit(rule)}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0 text-red-500 hover:text-red-700 hover:bg-red-50"
                        onClick={() => setDeleteRule(rule)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <RuleDialog
        open={dialogOpen}
        editRule={editRule}
        onClose={handleDialogClose}
        onSuccess={(msg) => showToast(msg, "success")}
        onError={(msg) => showToast(msg, "error")}
      />

      <ConfirmDeleteDialog
        rule={deleteRule}
        onClose={() => setDeleteRule(null)}
        onSuccess={(msg) => showToast(msg, "success")}
        onError={(msg) => showToast(msg, "error")}
      />
    </div>
  );
}
