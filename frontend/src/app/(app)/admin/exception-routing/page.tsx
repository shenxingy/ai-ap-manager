"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
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

interface ExceptionRoutingRule {
  id: string;
  exception_code: string;
  target_role: string;
  priority: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// ─── Constants ───

const TARGET_ROLES = ["AP_CLERK", "AP_ANALYST", "APPROVER", "ADMIN"];

const EXCEPTION_CODE_SUGGESTIONS = [
  "PRICE_MISMATCH",
  "QTY_MISMATCH",
  "MISSING_PO",
  "DUPLICATE_INVOICE",
  "VENDOR_MISMATCH",
  "LINE_MISMATCH",
  "TOLERANCE_EXCEEDED",
];

// ─── Helpers ───

function extractApiError(err: unknown): string {
  return (
    (err as { response?: { data?: { detail?: string } } })?.response?.data
      ?.detail ?? "Operation failed"
  );
}

// ─── Badges ───

function StatusBadge({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
        active
          ? "bg-green-100 text-green-700"
          : "bg-gray-100 text-gray-500"
      }`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${
          active ? "bg-green-500" : "bg-gray-400"
        }`}
      />
      {active ? "Active" : "Inactive"}
    </span>
  );
}

// ─── Toggle Switch ───

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed ${
        checked ? "bg-green-500" : "bg-gray-300"
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
          checked ? "translate-x-6" : "translate-x-1"
        }`}
      />
    </button>
  );
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
      className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white transition-opacity ${
        toast.type === "success" ? "bg-green-600" : "bg-red-600"
      }`}
    >
      {toast.message}
    </div>
  );
}

// ─── New Rule Dialog ───

interface NewRuleDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}

interface NewRuleForm {
  exception_code: string;
  target_role: string;
  priority: string;
  is_active: boolean;
}

const DEFAULT_FORM: NewRuleForm = {
  exception_code: "",
  target_role: "AP_ANALYST",
  priority: "0",
  is_active: true,
};

function NewRuleDialog({
  open,
  onClose,
  onSuccess,
  onError,
}: NewRuleDialogProps) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<NewRuleForm>(DEFAULT_FORM);
  const [codeCustom, setCodeCustom] = useState(false);

  const mutation = useMutation({
    mutationFn: async () => {
      const payload = {
        exception_code: form.exception_code.trim().toUpperCase(),
        target_role: form.target_role,
        priority: parseInt(form.priority, 10) || 0,
        is_active: form.is_active,
      };
      const res = await api.post<ExceptionRoutingRule>(
        "/admin/exception-routing",
        payload
      );
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["exception-routing-rules"] });
      onSuccess("Routing rule created");
      handleClose();
    },
    onError: (err) => onError(extractApiError(err)),
  });

  const handleClose = () => {
    onClose();
    setForm(DEFAULT_FORM);
    setCodeCustom(false);
  };

  const isValid = form.exception_code.trim().length > 0 && form.target_role;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Routing Rule</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label>
              Exception Code <span className="text-red-500">*</span>
            </Label>
            {!codeCustom ? (
              <div className="flex gap-2">
                <Select
                  value={form.exception_code}
                  onValueChange={(v) => setForm({ ...form, exception_code: v })}
                >
                  <SelectTrigger className="flex-1">
                    <SelectValue placeholder="Select code…" />
                  </SelectTrigger>
                  <SelectContent>
                    {EXCEPTION_CODE_SUGGESTIONS.map((code) => (
                      <SelectItem key={code} value={code}>
                        {code}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setCodeCustom(true);
                    setForm({ ...form, exception_code: "" });
                  }}
                >
                  Custom
                </Button>
              </div>
            ) : (
              <div className="flex gap-2">
                <Input
                  placeholder="e.g. TAX_MISMATCH"
                  value={form.exception_code}
                  onChange={(e) =>
                    setForm({ ...form, exception_code: e.target.value })
                  }
                  className="flex-1"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setCodeCustom(false);
                    setForm({ ...form, exception_code: "" });
                  }}
                >
                  Preset
                </Button>
              </div>
            )}
          </div>

          <div className="space-y-1.5">
            <Label>
              Target Role <span className="text-red-500">*</span>
            </Label>
            <Select
              value={form.target_role}
              onValueChange={(v) => setForm({ ...form, target_role: v })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TARGET_ROLES.map((role) => (
                  <SelectItem key={role} value={role}>
                    {role}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="nr-priority">
              Priority{" "}
              <span className="text-gray-400 font-normal text-xs">
                (higher = evaluated first)
              </span>
            </Label>
            <Input
              id="nr-priority"
              type="number"
              min={0}
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value })}
            />
          </div>

          <div className="flex items-center gap-3">
            <Label>Active</Label>
            <Toggle
              checked={form.is_active}
              onChange={(v) => setForm({ ...form, is_active: v })}
            />
            <span className="text-sm text-gray-600">
              {form.is_active ? "Active" : "Inactive"}
            </span>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            disabled={!isValid || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Creating…" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Page ───

export default function AdminExceptionRoutingPage() {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const { toast, showToast } = useToast();

  const { data: rules, isLoading } = useQuery<ExceptionRoutingRule[]>({
    queryKey: ["exception-routing-rules"],
    queryFn: () =>
      api
        .get<ExceptionRoutingRule[]>("/admin/exception-routing")
        .then((r) => r.data),
  });

  const toggleMutation = useMutation({
    mutationFn: async ({
      id,
      is_active,
    }: {
      id: string;
      is_active: boolean;
    }) => {
      const res = await api.patch<ExceptionRoutingRule>(
        `/admin/exception-routing/${id}`,
        { is_active }
      );
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["exception-routing-rules"] });
    },
    onError: (err) => showToast(extractApiError(err), "error"),
  });

  return (
    <div className="space-y-4">
      <ToastBanner toast={toast} />

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">
            Exception Routing
          </h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Rules that determine which role handles each exception type
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>New Rule</Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Exception Code</TableHead>
                <TableHead>Target Role</TableHead>
                <TableHead>Priority</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-24">Active</TableHead>
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
              {!isLoading && (!rules || rules.length === 0) && (
                <TableRow>
                  <TableCell
                    colSpan={5}
                    className="text-center text-gray-400 py-8"
                  >
                    No routing rules yet. Click New Rule to create one.
                  </TableCell>
                </TableRow>
              )}
              {rules?.map((rule) => (
                <TableRow key={rule.id}>
                  <TableCell>
                    <span className="font-mono text-sm font-medium bg-gray-100 px-2 py-0.5 rounded">
                      {rule.exception_code}
                    </span>
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-700">
                      {rule.target_role}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-gray-600">
                    {rule.priority}
                  </TableCell>
                  <TableCell>
                    <StatusBadge active={rule.is_active} />
                  </TableCell>
                  <TableCell>
                    <Toggle
                      checked={rule.is_active}
                      disabled={toggleMutation.isPending}
                      onChange={(v) =>
                        toggleMutation.mutate({ id: rule.id, is_active: v })
                      }
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <NewRuleDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSuccess={(msg) => showToast(msg, "success")}
        onError={(msg) => showToast(msg, "error")}
      />
    </div>
  );
}
