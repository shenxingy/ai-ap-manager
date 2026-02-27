"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
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
import api from "@/lib/api";

// ─── Types ───

interface RecurringPattern {
  id: string;
  vendor_id: string;
  frequency_days: number;
  avg_amount: number;
  tolerance_pct: number;
  auto_fast_track: boolean;
  last_detected_at: string | null;
  created_at: string;
  updated_at: string;
}

// ─── Helpers ───

function extractApiError(err: unknown): string {
  return (
    (err as { response?: { data?: { detail?: string } } })?.response?.data
      ?.detail ?? "Operation failed"
  );
}

function fmtCurrency(val: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(val);
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtFrequency(days: number): string {
  if (days === 7) return "Weekly";
  if (days === 14) return "Bi-weekly";
  if (days === 30 || days === 31) return "Monthly";
  if (days === 90) return "Quarterly";
  if (days === 365) return "Annual";
  return `Every ${days} days`;
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

// ─── Toggle ───

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

// ─── Page ───

export default function AdminRecurringPatternsPage() {
  const queryClient = useQueryClient();
  const { toast, showToast } = useToast();

  const { data: patterns, isLoading } = useQuery<RecurringPattern[]>({
    queryKey: ["recurring-patterns"],
    queryFn: () =>
      api
        .get<RecurringPattern[]>("/admin/recurring-patterns")
        .then((r) => r.data),
  });

  const detectMutation = useMutation({
    mutationFn: async () => {
      const res = await api.post<{ status: string; task_id?: string }>(
        "/admin/recurring-patterns/detect"
      );
      return res.data;
    },
    onSuccess: (data) => {
      showToast(
        data.status === "queued"
          ? "Detection task queued"
          : "Detection completed",
        "success"
      );
      queryClient.invalidateQueries({ queryKey: ["recurring-patterns"] });
    },
    onError: (err) => showToast(extractApiError(err), "error"),
  });

  const toggleMutation = useMutation({
    mutationFn: async ({
      id,
      auto_fast_track,
    }: {
      id: string;
      auto_fast_track: boolean;
    }) => {
      const res = await api.patch<RecurringPattern>(
        `/admin/recurring-patterns/${id}`,
        { auto_fast_track }
      );
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recurring-patterns"] });
    },
    onError: (err) => showToast(extractApiError(err), "error"),
  });

  return (
    <div className="space-y-4">
      <ToastBanner toast={toast} />

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">
            Recurring Patterns
          </h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Detected recurring invoice patterns from vendor history
          </p>
        </div>
        <Button
          onClick={() => detectMutation.mutate()}
          disabled={detectMutation.isPending}
        >
          <RefreshCw
            className={`h-4 w-4 mr-2 ${detectMutation.isPending ? "animate-spin" : ""}`}
          />
          {detectMutation.isPending ? "Detecting…" : "Run Detection"}
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Vendor ID</TableHead>
                <TableHead>Frequency</TableHead>
                <TableHead>Avg Amount</TableHead>
                <TableHead>Tolerance</TableHead>
                <TableHead>Auto Fast-Track</TableHead>
                <TableHead>Last Detected</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="text-center text-gray-400 py-8"
                  >
                    Loading…
                  </TableCell>
                </TableRow>
              )}
              {!isLoading && (!patterns || patterns.length === 0) && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="text-center text-gray-400 py-12"
                  >
                    <div className="flex flex-col items-center gap-2">
                      <p className="font-medium">
                        No recurring patterns detected yet.
                      </p>
                      <p className="text-xs">
                        Click Run Detection to scan vendor invoice history.
                      </p>
                    </div>
                  </TableCell>
                </TableRow>
              )}
              {patterns?.map((pattern) => (
                <TableRow key={pattern.id}>
                  <TableCell className="font-mono text-xs text-gray-500">
                    {pattern.vendor_id.slice(0, 8)}…
                  </TableCell>
                  <TableCell className="text-sm">
                    {fmtFrequency(pattern.frequency_days)}
                  </TableCell>
                  <TableCell className="text-sm font-medium">
                    {fmtCurrency(pattern.avg_amount)}
                  </TableCell>
                  <TableCell className="text-sm text-gray-600">
                    ±{(pattern.tolerance_pct * 100).toFixed(1)}%
                  </TableCell>
                  <TableCell>
                    <Toggle
                      checked={pattern.auto_fast_track}
                      disabled={toggleMutation.isPending}
                      onChange={(v) =>
                        toggleMutation.mutate({
                          id: pattern.id,
                          auto_fast_track: v,
                        })
                      }
                    />
                  </TableCell>
                  <TableCell className="text-sm text-gray-500">
                    {fmtDate(pattern.last_detected_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
