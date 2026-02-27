"use client";

import { useState, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Upload, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { format } from "date-fns";
import api from "@/lib/api";

// ─── Types ───

interface Invoice {
  id: string;
  invoice_number: string;
  vendor_name_raw: string;
  total_amount: number;
  status: string;
  fraud_score: number | null;
  created_at: string;
}

interface InvoicesResponse {
  items: Invoice[];
  total: number;
  page: number;
  page_size: number;
}

// ─── Fraud Badge ───

const FRAUD_COLORS: Record<string, string> = {
  LOW: "🟢",
  MEDIUM: "🟡",
  HIGH: "🔴",
  CRITICAL: "🔴🔴",
};

function fraudBadge(score: number | null): string {
  if (score === null) return "—";
  if (score >= 0.9) return FRAUD_COLORS.CRITICAL;
  if (score >= 0.7) return FRAUD_COLORS.HIGH;
  if (score >= 0.4) return FRAUD_COLORS.MEDIUM;
  return FRAUD_COLORS.LOW;
}

// ─── Status Badge ───

const STATUS_VARIANTS: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  RECEIVED: "outline",
  PROCESSING: "secondary",
  MATCHED: "default",
  EXCEPTION: "destructive",
  APPROVED: "default",
  PAID: "default",
};

// ─── Upload Dialog ───

function UploadDialog({ onSuccess }: { onSuccess: () => void }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const uploadFile = async (file: File) => {
    setUploading(true);
    setUploadError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await api.post("/invoices/upload", form);
      const invoiceId = response.data.invoice_id;
      setOpen(false);
      onSuccess();
      // Redirect to the new invoice detail page
      router.push(`/invoices/${invoiceId}`);
    } catch {
      setUploadError("Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  };

  return (
    <Dialog open={open} onOpenChange={(newOpen) => {
      setOpen(newOpen);
      if (newOpen) {
        setUploadError(null);
      }
    }}>
      <DialogTrigger asChild>
        <Button>
          <Upload className="h-4 w-4 mr-2" />
          Upload Invoice
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload Invoice</DialogTitle>
        </DialogHeader>
        {uploadError && (
          <p className="text-sm text-red-600 bg-red-50 p-3 rounded">
            {uploadError}
          </p>
        )}
        <div
          className={`border-2 border-dashed rounded-lg p-10 text-center transition-colors ${
            uploading ? "border-gray-300 bg-gray-50 cursor-not-allowed" : dragging ? "border-blue-500 bg-blue-50 cursor-pointer" : "border-gray-300 hover:border-gray-400 cursor-pointer"
          }`}
          onDragOver={(e) => { if (!uploading) { e.preventDefault(); setDragging(true); } }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => !uploading && fileRef.current?.click()}
        >
          {uploading ? (
            <Loader2 className="h-8 w-8 mx-auto text-blue-500 mb-3 animate-spin" />
          ) : (
            <Upload className="h-8 w-8 mx-auto text-gray-400 mb-3" />
          )}
          <p className="text-sm text-gray-600">
            {uploading ? "Uploading..." : "Drag & drop or click to select"}
          </p>
          <p className="text-xs text-gray-400 mt-1">PDF, PNG, JPG accepted</p>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,image/*"
            className="hidden"
            disabled={uploading}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadFile(f); }}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Page ───

const STATUS_OPTIONS = ["ALL", "RECEIVED", "PROCESSING", "MATCHED", "EXCEPTION", "APPROVED", "PAID"];

export default function InvoicesPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("ALL");

  const { data } = useQuery<InvoicesResponse>({
    queryKey: ["invoices", page, statusFilter],
    queryFn: () => {
      const params = new URLSearchParams({ page: String(page), page_size: "20" });
      if (statusFilter !== "ALL") params.set("status", statusFilter);
      return api.get(`/invoices?${params}`).then((r) => r.data);
    },
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / 20));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-900">Invoices</h2>
        <UploadDialog onSuccess={() => queryClient.invalidateQueries({ queryKey: ["invoices"] })} />
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-3">
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(1); }}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>{s}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-sm text-gray-500">{total} invoices</span>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Invoice #</TableHead>
                <TableHead>Vendor</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Fraud</TableHead>
                <TableHead>Received</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-gray-400 py-8">
                    No invoices found.
                  </TableCell>
                </TableRow>
              )}
              {items.map((inv) => (
                <TableRow
                  key={inv.id}
                  className="cursor-pointer hover:bg-gray-50"
                  onClick={() => router.push(`/invoices/${inv.id}`)}
                >
                  <TableCell className="font-medium">{inv.invoice_number || "—"}</TableCell>
                  <TableCell>{inv.vendor_name_raw || "—"}</TableCell>
                  <TableCell className="text-right">
                    {inv.total_amount != null
                      ? `$${inv.total_amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                      : "—"}
                  </TableCell>
                  <TableCell>
                    <Badge variant={STATUS_VARIANTS[inv.status] ?? "outline"}>
                      {inv.status}
                    </Badge>
                  </TableCell>
                  <TableCell title={inv.fraud_score != null ? `Fraud score: ${(inv.fraud_score * 100).toFixed(0)}%` : "No fraud data"}>{fraudBadge(inv.fraud_score)}</TableCell>
                  <TableCell className="text-sm text-gray-500">
                    {format(new Date(inv.created_at), "MMM d, yyyy")}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Pagination */}
      <div className="flex items-center justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page <= 1}
        >
          <ChevronLeft className="h-4 w-4" />
          Previous
        </Button>
        <span className="text-sm text-gray-600">
          Page {page} of {totalPages}
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          disabled={page >= totalPages}
        >
          Next
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
