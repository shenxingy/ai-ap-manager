"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { useAuthStore } from "@/store/auth";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { format } from "date-fns";
import api from "@/lib/api";

// ─── Types ───

interface PaymentRun {
  id: string;
  run_name: string;
  vendor_name: string | null;
  scheduled_date: string;
  invoice_count: number;
  total_amount: number;
  currency: string;
  status: "pending" | "processing" | "completed" | "cancelled";
  frequency: string;
  payment_method: string;
  created_at: string;
}

interface PaymentRunDetail extends PaymentRun {
  invoices: RunInvoice[];
}

interface RunInvoice {
  id: string;
  invoice_number: string;
  vendor_name: string;
  amount: number;
  currency: string;
}

interface PaymentRunListResponse {
  items: PaymentRun[];
  total: number;
}

// ─── Constants ───

const STATUS_CONFIG: Record<
  string,
  { label: string; className: string }
> = {
  pending: { label: "Pending", className: "bg-yellow-100 text-yellow-700 border-yellow-200" },
  processing: { label: "Processing", className: "bg-blue-100 text-blue-700 border-blue-200" },
  completed: { label: "Completed", className: "bg-green-100 text-green-700 border-green-200" },
  cancelled: { label: "Cancelled", className: "bg-gray-100 text-gray-500 border-gray-200" },
};

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

// ─── Status Badge ───

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending;
  return (
    <Badge variant="outline" className={cfg.className}>
      {cfg.label}
    </Badge>
  );
}

// ─── Generate Dialog ───

interface GenerateDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}

function GenerateRunDialog({ open, onClose, onSuccess, onError }: GenerateDialogProps) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    frequency: "weekly",
    payment_method: "ACH",
    scheduled_date: "",
  });

  const mutation = useMutation({
    mutationFn: () =>
      api.post("/payment-runs/generate", form).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["payment-runs"] });
      onSuccess("Payment run generated successfully");
      onClose();
      setForm({ frequency: "weekly", payment_method: "ACH", scheduled_date: "" });
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Failed to generate payment run";
      onError(msg);
    },
  });

  const handleClose = () => {
    onClose();
    setForm({ frequency: "weekly", payment_method: "ACH", scheduled_date: "" });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Generate Payment Run</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label>Frequency</Label>
            <Select
              value={form.frequency}
              onValueChange={(v) => setForm({ ...form, frequency: v })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="weekly">Weekly</SelectItem>
                <SelectItem value="biweekly">Biweekly</SelectItem>
                <SelectItem value="monthly">Monthly</SelectItem>
                <SelectItem value="adhoc">Ad-hoc</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Payment Method</Label>
            <Select
              value={form.payment_method}
              onValueChange={(v) => setForm({ ...form, payment_method: v })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ACH">ACH</SelectItem>
                <SelectItem value="WIRE">Wire Transfer</SelectItem>
                <SelectItem value="CHECK">Check</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="gr-date">Scheduled Date</Label>
            <Input
              id="gr-date"
              type="date"
              value={form.scheduled_date}
              onChange={(e) => setForm({ ...form, scheduled_date: e.target.value })}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            disabled={!form.scheduled_date || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Generating…" : "Generate"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Execute Confirm Dialog ───

interface ExecuteDialogProps {
  run: PaymentRun | null;
  onClose: () => void;
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}

function ExecuteDialog({ run, onClose, onSuccess, onError }: ExecuteDialogProps) {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () =>
      api.post(`/payment-runs/${run!.id}/execute`).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["payment-runs"] });
      onSuccess("Payment run execution started");
      onClose();
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Failed to execute payment run";
      onError(msg);
    },
  });

  return (
    <Dialog open={!!run} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Execute Payment Run</DialogTitle>
        </DialogHeader>
        {run && (
          <div className="py-2 space-y-2">
            <p className="text-sm text-gray-600">
              Are you sure you want to execute <strong>{run.run_name}</strong>?
            </p>
            <p className="text-sm text-gray-500">
              This will process{" "}
              <strong>{run.invoice_count} invoice(s)</strong> totalling{" "}
              <strong>
                {run.currency}{" "}
                {run.total_amount.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                })}
              </strong>{" "}
              via <strong>{run.payment_method}</strong>.
            </p>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Executing…" : "Confirm Execute"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Run Detail Sheet ───

interface RunDetailSheetProps {
  runId: string | null;
  onClose: () => void;
}

function RunDetailSheet({ runId, onClose }: RunDetailSheetProps) {
  const { data, isLoading } = useQuery<PaymentRunDetail>({
    queryKey: ["payment-run-detail", runId],
    queryFn: () =>
      api.get(`/payment-runs/${runId}`).then((r) => r.data),
    enabled: !!runId,
  });

  return (
    <Sheet open={!!runId} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{data?.run_name ?? "Payment Run Detail"}</SheetTitle>
        </SheetHeader>
        {isLoading && (
          <p className="text-sm text-gray-400 mt-6">Loading…</p>
        )}
        {data && (
          <div className="mt-6 space-y-4">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-gray-500">Status</p>
                <StatusBadge status={data.status} />
              </div>
              <div>
                <p className="text-gray-500">Method</p>
                <p className="font-medium">{data.payment_method}</p>
              </div>
              <div>
                <p className="text-gray-500">Frequency</p>
                <p className="font-medium capitalize">{data.frequency}</p>
              </div>
              <div>
                <p className="text-gray-500">Scheduled Date</p>
                <p className="font-medium">
                  {format(new Date(data.scheduled_date), "MMM d, yyyy")}
                </p>
              </div>
              <div>
                <p className="text-gray-500">Total Amount</p>
                <p className="font-medium">
                  {data.currency}{" "}
                  {data.total_amount.toLocaleString("en-US", {
                    minimumFractionDigits: 2,
                  })}
                </p>
              </div>
              <div>
                <p className="text-gray-500">Invoices</p>
                <p className="font-medium">{data.invoice_count}</p>
              </div>
            </div>

            <div>
              <h3 className="font-semibold text-sm mb-2">Included Invoices</h3>
              {data.invoices?.length === 0 && (
                <p className="text-sm text-gray-400">No invoices attached.</p>
              )}
              <div className="rounded-lg border divide-y">
                {(data.invoices ?? []).map((inv) => (
                  <div key={inv.id} className="px-3 py-2 text-sm flex items-center justify-between">
                    <div>
                      <p className="font-medium">{inv.invoice_number}</p>
                      <p className="text-gray-500 text-xs">{inv.vendor_name}</p>
                    </div>
                    <p className="font-medium tabular-nums">
                      {inv.currency}{" "}
                      {inv.amount.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

// ─── Page ───

export default function PaymentRunsPage() {
  const router = useRouter();
  const { user } = useAuthStore();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (user && user.role !== "ADMIN") {
      router.push("/unauthorized");
    }
  }, [user, router]);

  const [generateOpen, setGenerateOpen] = useState(false);
  const [executeRun, setExecuteRun] = useState<PaymentRun | null>(null);
  const [viewRunId, setViewRunId] = useState<string | null>(null);
  const { toast, showToast } = useToast();

  const { data, isLoading } = useQuery<PaymentRunListResponse>({
    queryKey: ["payment-runs"],
    queryFn: () => api.get("/payment-runs").then((r) => r.data),
    refetchInterval: (query) => {
      const runs = (query.state.data as PaymentRunListResponse | undefined)?.items ?? [];
      return runs.some((r) => r.status === "processing") ? 10000 : false;
    },
  });

  const cancelRun = useMutation({
    mutationFn: (id: string) =>
      api.patch(`/payment-runs/${id}/cancel`).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["payment-runs"] });
      showToast("Payment run cancelled", "success");
    },
    onError: () => showToast("Failed to cancel payment run", "error"),
  });

  const runs = data?.items ?? [];

  return (
    <div className="space-y-4">
      <ToastBanner toast={toast} />

      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-900">Payment Runs</h2>
        <Button onClick={() => setGenerateOpen(true)}>Generate Run</Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Run Name</TableHead>
                <TableHead>Vendor</TableHead>
                <TableHead>Scheduled Date</TableHead>
                <TableHead className="text-right"># Invoices</TableHead>
                <TableHead className="text-right">Total Amount</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-40" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-gray-400 py-8">
                    Loading…
                  </TableCell>
                </TableRow>
              )}
              {!isLoading && runs.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-gray-400 py-8">
                    No payment runs found.
                  </TableCell>
                </TableRow>
              )}
              {runs.map((run) => (
                <TableRow key={run.id}>
                  <TableCell className="font-medium">{run.run_name}</TableCell>
                  <TableCell className="text-gray-600">
                    {run.vendor_name ?? "—"}
                  </TableCell>
                  <TableCell className="text-sm text-gray-600">
                    {format(new Date(run.scheduled_date), "MMM d, yyyy")}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {run.invoice_count}
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-medium">
                    {run.currency}{" "}
                    {run.total_amount.toLocaleString("en-US", {
                      minimumFractionDigits: 2,
                    })}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={run.status} />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      {run.status === "pending" && (
                        <>
                          <Button
                            size="sm"
                            onClick={() => setExecuteRun(run)}
                          >
                            Execute
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="text-red-600 hover:text-red-700 hover:bg-red-50"
                            disabled={cancelRun.isPending}
                            onClick={() => cancelRun.mutate(run.id)}
                          >
                            Cancel
                          </Button>
                        </>
                      )}
                      {run.status === "completed" && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setViewRunId(run.id)}
                        >
                          View
                        </Button>
                      )}
                      {run.status === "processing" && (
                        <span className="text-xs text-blue-600 animate-pulse font-medium">
                          Processing…
                        </span>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <GenerateRunDialog
        open={generateOpen}
        onClose={() => setGenerateOpen(false)}
        onSuccess={(msg) => showToast(msg, "success")}
        onError={(msg) => showToast(msg, "error")}
      />
      <ExecuteDialog
        run={executeRun}
        onClose={() => setExecuteRun(null)}
        onSuccess={(msg) => showToast(msg, "success")}
        onError={(msg) => showToast(msg, "error")}
      />
      <RunDetailSheet
        runId={viewRunId}
        onClose={() => setViewRunId(null)}
      />
    </div>
  );
}
