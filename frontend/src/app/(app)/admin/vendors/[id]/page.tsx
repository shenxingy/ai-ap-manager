"use client";

import { useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Upload, FileText } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
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

interface VendorDetail {
  id: string;
  name: string;
  tax_id: string | null;
  payment_terms: number;
  currency: string;
  is_active: boolean;
  invoice_count: number;
  email: string | null;
  address: string | null;
  created_at: string;
  updated_at: string;
}

interface ComplianceDoc {
  id: string;
  vendor_id: string;
  doc_type: string;
  status: string;
  expiry_date: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

// ─── Constants ───

const DOC_TYPES = ["W9", "W8BEN", "VAT", "insurance", "other"];

const DOC_TYPE_LABELS: Record<string, string> = {
  W9: "W-9",
  W8BEN: "W-8BEN",
  VAT: "VAT Certificate",
  insurance: "Insurance",
  other: "Other",
};

// ─── Helpers ───

function paymentTermsLabel(days: number): string {
  if (days === 0) return "Immediate";
  return `NET ${days}`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function isExpiringSoon(expiryDate: string | null): boolean {
  if (!expiryDate) return false;
  const diff = new Date(expiryDate).getTime() - Date.now();
  return diff > 0 && diff < 30 * 24 * 60 * 60 * 1000;
}

function isExpired(expiryDate: string | null): boolean {
  if (!expiryDate) return false;
  return new Date(expiryDate).getTime() < Date.now();
}

function extractApiError(err: unknown): string {
  return (
    (err as { response?: { data?: { detail?: string } } })?.response?.data
      ?.detail ?? "Operation failed"
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
      className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white ${
        toast.type === "success" ? "bg-green-600" : "bg-red-600"
      }`}
    >
      {toast.message}
    </div>
  );
}

// ─── Doc Status Badge ───

function DocStatusBadge({
  status,
  expiryDate,
}: {
  status: string;
  expiryDate: string | null;
}) {
  if (status === "missing") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700">
        <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
        Missing
      </span>
    );
  }
  if (status === "expired" || isExpired(expiryDate)) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700">
        <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
        Expired
      </span>
    );
  }
  if (isExpiringSoon(expiryDate)) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-orange-100 text-orange-700">
        <span className="w-1.5 h-1.5 rounded-full bg-orange-500" />
        Expiring Soon
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700">
      <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
      Active
    </span>
  );
}

// ─── Upload Doc Form ───

interface UploadFormProps {
  vendorId: string;
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}

function UploadDocForm({ vendorId, onSuccess, onError }: UploadFormProps) {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [docType, setDocType] = useState("W9");
  const [file, setFile] = useState<File | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("No file selected");
      const fd = new FormData();
      fd.append("doc_type", docType);
      fd.append("file", file);
      const res = await api.post<ComplianceDoc>(
        `/vendors/${vendorId}/compliance-docs`,
        fd,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendor-compliance", vendorId] });
      onSuccess("Document uploaded successfully");
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
    },
    onError: (err) => onError(extractApiError(err)),
  });

  return (
    <div className="flex items-end gap-3 flex-wrap">
      <div className="space-y-1.5">
        <Label className="text-xs">Document Type</Label>
        <Select value={docType} onValueChange={setDocType}>
          <SelectTrigger className="w-44 h-8 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DOC_TYPES.map((t) => (
              <SelectItem key={t} value={t}>
                {DOC_TYPE_LABELS[t] ?? t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">File</Label>
        <input
          ref={fileRef}
          type="file"
          className="text-sm text-gray-600 h-8 border border-gray-300 rounded px-2 py-1 cursor-pointer"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </div>
      <Button
        size="sm"
        disabled={!file || mutation.isPending}
        onClick={() => mutation.mutate()}
        className="h-8"
      >
        <Upload className="h-3.5 w-3.5 mr-1.5" />
        {mutation.isPending ? "Uploading…" : "Upload"}
      </Button>
    </div>
  );
}

// ─── Page ───

export default function VendorDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { toast, showToast } = useToast();

  const { data: vendor, isLoading: vendorLoading } = useQuery<VendorDetail>({
    queryKey: ["vendor", id],
    queryFn: () => api.get<VendorDetail>(`/vendors/${id}`).then((r) => r.data),
    enabled: !!id,
  });

  const { data: docs, isLoading: docsLoading } = useQuery<ComplianceDoc[]>({
    queryKey: ["vendor-compliance", id],
    queryFn: () =>
      api
        .get<ComplianceDoc[]>(`/vendors/${id}/compliance-docs`)
        .then((r) => r.data),
    enabled: !!id,
  });

  if (vendorLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-gray-400 text-sm">
        Loading…
      </div>
    );
  }

  if (!vendor) {
    return (
      <div className="flex items-center justify-center py-16 text-gray-400 text-sm">
        Vendor not found.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <ToastBanner toast={toast} />

      {/* Header */}
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.back()}
          className="h-8 px-2"
        >
          <ArrowLeft className="h-4 w-4 mr-1" />
          Back
        </Button>
        <div>
          <h2 className="text-2xl font-bold text-gray-900">{vendor.name}</h2>
          <p className="text-sm text-gray-500 mt-0.5">Vendor Detail</p>
        </div>
      </div>

      {/* Vendor Info */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold text-gray-700">
            Vendor Information
          </CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <dt className="text-xs text-gray-500 mb-0.5">Name</dt>
              <dd className="text-sm font-medium">{vendor.name}</dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500 mb-0.5">Tax ID</dt>
              <dd className="text-sm font-medium">
                {vendor.tax_id ?? <span className="text-gray-300">—</span>}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500 mb-0.5">Payment Terms</dt>
              <dd className="text-sm font-medium">
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-700">
                  {paymentTermsLabel(vendor.payment_terms)}
                </span>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500 mb-0.5">Currency</dt>
              <dd className="text-sm font-medium">{vendor.currency}</dd>
            </div>
            {vendor.email && (
              <div>
                <dt className="text-xs text-gray-500 mb-0.5">Email</dt>
                <dd className="text-sm font-medium">{vendor.email}</dd>
              </div>
            )}
            {vendor.address && (
              <div className="col-span-2">
                <dt className="text-xs text-gray-500 mb-0.5">Address</dt>
                <dd className="text-sm font-medium">{vendor.address}</dd>
              </div>
            )}
            <div>
              <dt className="text-xs text-gray-500 mb-0.5">Status</dt>
              <dd>
                <span
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                    vendor.is_active
                      ? "bg-green-100 text-green-700"
                      : "bg-gray-100 text-gray-500"
                  }`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      vendor.is_active ? "bg-green-500" : "bg-gray-400"
                    }`}
                  />
                  {vendor.is_active ? "Active" : "Inactive"}
                </span>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500 mb-0.5">Total Invoices</dt>
              <dd className="text-sm font-medium">
                {vendor.invoice_count.toLocaleString()}
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {/* Compliance Documents */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold text-gray-700">
              Compliance Documents
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <UploadDocForm
            vendorId={id}
            onSuccess={(msg) => showToast(msg, "success")}
            onError={(msg) => showToast(msg, "error")}
          />

          {docsLoading ? (
            <div className="text-sm text-gray-400 py-4 text-center">
              Loading…
            </div>
          ) : !docs || docs.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-8 text-gray-400">
              <FileText className="h-8 w-8" />
              <p className="text-sm">No compliance documents uploaded yet.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {docs.map((doc) => (
                <div
                  key={doc.id}
                  className="rounded-lg border border-gray-200 p-4 space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">
                      {DOC_TYPE_LABELS[doc.doc_type] ?? doc.doc_type}
                    </span>
                    <DocStatusBadge
                      status={doc.status}
                      expiryDate={doc.expiry_date}
                    />
                  </div>
                  <div className="text-xs text-gray-500">
                    {doc.expiry_date ? (
                      <>Expires: {fmtDate(doc.expiry_date)}</>
                    ) : (
                      "No expiry date"
                    )}
                  </div>
                  {doc.notes && (
                    <div className="text-xs text-gray-400 italic">
                      {doc.notes}
                    </div>
                  )}
                  <div className="text-xs text-gray-400">
                    Uploaded: {fmtDate(doc.created_at)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
