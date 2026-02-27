"use client";

import { useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Upload, FileText, Trash2, Plus } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
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

interface VendorAlias {
  id: string;
  alias: string;
  created_at: string;
}

interface InvoiceStub {
  id: string;
  invoice_number: string | null;
  status: string;
  total_amount: string | null;
  currency: string | null;
  created_at: string;
}

interface VendorDetail {
  id: string;
  name: string;
  tax_id: string | null;
  bank_account: string | null;
  bank_routing: string | null;
  payment_terms: number;
  currency: string;
  is_active: boolean;
  email: string | null;
  address: string | null;
  created_at: string;
  updated_at: string;
  aliases: VendorAlias[];
  recent_invoices: InvoiceStub[];
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

const PAYMENT_TERMS_OPTIONS = [
  { label: "Immediate", value: 0 },
  { label: "NET 30", value: 30 },
  { label: "NET 60", value: 60 },
  { label: "NET 90", value: 90 },
];

// ─── Helpers ───

function paymentTermsLabel(days: number): string {
  const opt = PAYMENT_TERMS_OPTIONS.find((o) => o.value === days);
  return opt ? opt.label : `NET ${days}`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function fmtAmount(amount: string | null, currency: string | null): string {
  if (amount == null) return "—";
  const num = parseFloat(amount);
  if (isNaN(num)) return amount;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency ?? "USD",
    minimumFractionDigits: 2,
  }).format(num);
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

// ─── Invoice Status Badge ───

function InvoiceStatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    approved: "bg-green-100 text-green-700",
    pending: "bg-yellow-100 text-yellow-700",
    rejected: "bg-red-100 text-red-700",
    paid: "bg-blue-100 text-blue-700",
    cancelled: "bg-gray-100 text-gray-500",
  };
  const cls = colorMap[status] ?? "bg-gray-100 text-gray-500";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}

// ─── Page ───

export default function VendorDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { toast, showToast } = useToast();

  // Edit form state
  const [editing, setEditing] = useState(false);
  const [formName, setFormName] = useState("");
  const [formTaxId, setFormTaxId] = useState("");
  const [formCurrency, setFormCurrency] = useState("USD");
  const [formPaymentTerms, setFormPaymentTerms] = useState(30);
  const [formBankAccount, setFormBankAccount] = useState("");
  const [formBankRouting, setFormBankRouting] = useState("");
  const [formEmail, setFormEmail] = useState("");
  const [formAddress, setFormAddress] = useState("");
  const [formIsActive, setFormIsActive] = useState(true);
  const [originalBankAccount, setOriginalBankAccount] = useState("");

  // Alias add input
  const [newAlias, setNewAlias] = useState("");

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

  const startEditing = () => {
    if (!vendor) return;
    setFormName(vendor.name);
    setFormTaxId(vendor.tax_id ?? "");
    setFormCurrency(vendor.currency);
    setFormPaymentTerms(vendor.payment_terms);
    setFormBankAccount(vendor.bank_account ?? "");
    setFormBankRouting(vendor.bank_routing ?? "");
    setFormEmail(vendor.email ?? "");
    setFormAddress(vendor.address ?? "");
    setFormIsActive(vendor.is_active);
    setOriginalBankAccount(vendor.bank_account ?? "");
    setEditing(true);
  };

  const bankAccountChanged = editing && formBankAccount !== originalBankAccount;

  const saveMutation = useMutation({
    mutationFn: () =>
      api
        .patch(`/vendors/${id}`, {
          name: formName.trim(),
          tax_id: formTaxId.trim() || null,
          currency: formCurrency,
          payment_terms: formPaymentTerms,
          bank_account: formBankAccount.trim() || null,
          bank_routing: formBankRouting.trim() || null,
          email: formEmail.trim() || null,
          address: formAddress.trim() || null,
          is_active: formIsActive,
        })
        .then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendor", id] });
      showToast("Vendor updated successfully", "success");
      setEditing(false);
    },
    onError: (err) => showToast(extractApiError(err), "error"),
  });

  const addAliasMutation = useMutation({
    mutationFn: () =>
      api
        .post(`/vendors/${id}/aliases`, { alias_name: newAlias.trim() })
        .then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendor", id] });
      showToast("Alias added", "success");
      setNewAlias("");
    },
    onError: (err) => showToast(extractApiError(err), "error"),
  });

  const removeAliasMutation = useMutation({
    mutationFn: (aliasId: string) =>
      api.delete(`/vendors/${id}/aliases/${aliasId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendor", id] });
      showToast("Alias removed", "success");
    },
    onError: (err) => showToast(extractApiError(err), "error"),
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
      <div className="flex items-center justify-between">
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
        {!editing && (
          <Button size="sm" variant="outline" onClick={startEditing}>
            Edit
          </Button>
        )}
      </div>

      {/* Edit Form */}
      {editing ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold text-gray-700">
              Edit Vendor
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="name">
                  Name <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="name"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tax-id">Tax ID</Label>
                <Input
                  id="tax-id"
                  placeholder="12-3456789"
                  value={formTaxId}
                  onChange={(e) => setFormTaxId(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Currency</Label>
                <Input
                  value={formCurrency}
                  onChange={(e) => setFormCurrency(e.target.value.toUpperCase())}
                  placeholder="USD"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Payment Terms</Label>
                <Select
                  value={String(formPaymentTerms)}
                  onValueChange={(v) => setFormPaymentTerms(Number(v))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PAYMENT_TERMS_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={String(opt.value)}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="bank-account">Bank Account</Label>
                <Input
                  id="bank-account"
                  value={formBankAccount}
                  onChange={(e) => setFormBankAccount(e.target.value)}
                />
                {bankAccountChanged && (
                  <p className="text-xs text-orange-600">
                    ⚠️ Changing bank account will trigger a fraud signal.
                  </p>
                )}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="bank-routing">Bank Routing</Label>
                <Input
                  id="bank-routing"
                  value={formBankRouting}
                  onChange={(e) => setFormBankRouting(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={formEmail}
                  onChange={(e) => setFormEmail(e.target.value)}
                />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="address">Address</Label>
                <Input
                  id="address"
                  value={formAddress}
                  onChange={(e) => setFormAddress(e.target.value)}
                />
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Label>Active</Label>
              <button
                type="button"
                role="switch"
                aria-checked={formIsActive}
                onClick={() => setFormIsActive(!formIsActive)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
                  formIsActive ? "bg-green-500" : "bg-gray-300"
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    formIsActive ? "translate-x-6" : "translate-x-1"
                  }`}
                />
              </button>
              <span className="text-sm text-gray-600">
                {formIsActive ? "Active" : "Inactive"}
              </span>
            </div>
            <div className="flex items-center gap-2 pt-2 border-t border-gray-100">
              <Button
                disabled={!formName.trim() || saveMutation.isPending}
                onClick={() => saveMutation.mutate()}
              >
                {saveMutation.isPending ? "Saving…" : "Save Changes"}
              </Button>
              <Button
                variant="outline"
                onClick={() => setEditing(false)}
                disabled={saveMutation.isPending}
              >
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        /* Read-only info */
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
              {vendor.bank_account && (
                <div>
                  <dt className="text-xs text-gray-500 mb-0.5">Bank Account</dt>
                  <dd className="text-sm font-medium font-mono">
                    ••••{vendor.bank_account.slice(-4)}
                  </dd>
                </div>
              )}
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
            </dl>
          </CardContent>
        </Card>
      )}

      {/* Aliases */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold text-gray-700">
            Aliases
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {vendor.aliases.length === 0 ? (
            <p className="text-sm text-gray-400">No aliases configured.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {vendor.aliases.map((alias) => (
                <span
                  key={alias.id}
                  className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-gray-100 text-sm text-gray-700"
                >
                  {alias.alias}
                  <button
                    onClick={() => removeAliasMutation.mutate(alias.id)}
                    disabled={removeAliasMutation.isPending}
                    className="ml-1 text-gray-400 hover:text-red-500 transition-colors"
                    aria-label={`Remove alias ${alias.alias}`}
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className="flex items-center gap-2 pt-1">
            <Input
              placeholder="Add alias…"
              value={newAlias}
              onChange={(e) => setNewAlias(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && newAlias.trim()) {
                  addAliasMutation.mutate();
                }
              }}
              className="max-w-xs h-8 text-sm"
            />
            <Button
              size="sm"
              variant="outline"
              className="h-8"
              disabled={!newAlias.trim() || addAliasMutation.isPending}
              onClick={() => addAliasMutation.mutate()}
            >
              <Plus className="h-3.5 w-3.5 mr-1" />
              Add
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Recent Invoices */}
      {vendor.recent_invoices && vendor.recent_invoices.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold text-gray-700">
              Recent Invoices
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="divide-y divide-gray-100">
              {vendor.recent_invoices.map((inv) => (
                <div
                  key={inv.id}
                  className="flex items-center justify-between py-2.5 text-sm"
                >
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-gray-700">
                      {inv.invoice_number ?? inv.id.slice(0, 8)}
                    </span>
                    <InvoiceStatusBadge status={inv.status} />
                  </div>
                  <div className="flex items-center gap-4 text-gray-500">
                    <span>{fmtAmount(inv.total_amount, inv.currency)}</span>
                    <span className="text-xs">{fmtDate(inv.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

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
