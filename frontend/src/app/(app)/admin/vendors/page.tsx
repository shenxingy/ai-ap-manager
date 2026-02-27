"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
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

interface VendorListItem {
  id: string;
  name: string;
  tax_id: string | null;
  payment_terms: number;
  currency: string;
  is_active: boolean;
  invoice_count: number;
}

interface VendorAlias {
  id: string;
  alias: string;
  created_at: string;
}

interface VendorDetail extends VendorListItem {
  bank_account: string | null;
  bank_routing: string | null;
  email: string | null;
  address: string | null;
  created_at: string;
  updated_at: string;
  aliases: VendorAlias[];
}

interface VendorListResponse {
  items: VendorListItem[];
  total: number;
  page: number;
  page_size: number;
}

// ─── Constants ───

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

// ─── Vendor Form ───

interface VendorFormState {
  name: string;
  aliases: string; // comma-separated input
  payment_terms: number;
  tax_id: string;
  is_active: boolean;
}

const DEFAULT_FORM: VendorFormState = {
  name: "",
  aliases: "",
  payment_terms: 30,
  tax_id: "",
  is_active: true,
};

// ─── Create Vendor Dialog ───

interface CreateDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}

function CreateVendorDialog({
  open,
  onClose,
  onSuccess,
  onError,
}: CreateDialogProps) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<VendorFormState>(DEFAULT_FORM);

  const mutation = useMutation({
    mutationFn: async () => {
      const payload = {
        name: form.name.trim(),
        tax_id: form.tax_id.trim() || null,
        payment_terms: form.payment_terms,
        is_active: form.is_active,
      };
      const res = await api.post<VendorDetail>("/vendors", payload);
      const vendor = res.data;

      // Add each alias via the alias sub-endpoint
      const aliasNames = form.aliases
        .split(",")
        .map((a) => a.trim())
        .filter(Boolean);
      for (const alias_name of aliasNames) {
        await api.post(`/vendors/${vendor.id}/aliases`, { alias_name });
      }
      return vendor;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-vendors"] });
      onSuccess("Vendor created successfully");
      handleClose();
    },
    onError: (err) => onError(extractApiError(err)),
  });

  const handleClose = () => {
    onClose();
    setForm(DEFAULT_FORM);
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Vendor</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="cv-name">
              Name <span className="text-red-500">*</span>
            </Label>
            <Input
              id="cv-name"
              placeholder="Acme Corp"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="cv-aliases">
              Aliases{" "}
              <span className="text-gray-400 font-normal text-xs">
                (comma-separated)
              </span>
            </Label>
            <Input
              id="cv-aliases"
              placeholder="Acme, ACME Corporation"
              value={form.aliases}
              onChange={(e) => setForm({ ...form, aliases: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Payment Terms</Label>
            <Select
              value={String(form.payment_terms)}
              onValueChange={(v) =>
                setForm({ ...form, payment_terms: Number(v) })
              }
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
            <Label htmlFor="cv-tax-id">Tax ID</Label>
            <Input
              id="cv-tax-id"
              placeholder="12-3456789"
              value={form.tax_id}
              onChange={(e) => setForm({ ...form, tax_id: e.target.value })}
            />
          </div>
          <div className="flex items-center gap-3">
            <Label>Active</Label>
            <button
              type="button"
              role="switch"
              aria-checked={form.is_active}
              onClick={() => setForm({ ...form, is_active: !form.is_active })}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
                form.is_active ? "bg-green-500" : "bg-gray-300"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  form.is_active ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
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
            disabled={!form.name.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Creating…" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Edit Vendor Dialog ───

interface EditDialogProps {
  vendorId: string | null;
  onClose: () => void;
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}

function EditVendorDialog({
  vendorId,
  onClose,
  onSuccess,
  onError,
}: EditDialogProps) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<VendorFormState>(DEFAULT_FORM);
  const [originalAliases, setOriginalAliases] = useState<VendorAlias[]>([]);

  const { data: detail, isLoading } = useQuery<VendorDetail>({
    queryKey: ["vendor-detail", vendorId],
    queryFn: () =>
      api.get<VendorDetail>(`/vendors/${vendorId}`).then((r) => r.data),
    enabled: !!vendorId,
  });

  useEffect(() => {
    if (detail) {
      setForm({
        name: detail.name,
        aliases: detail.aliases.map((a) => a.alias).join(", "),
        payment_terms: detail.payment_terms,
        tax_id: detail.tax_id ?? "",
        is_active: detail.is_active,
      });
      setOriginalAliases(detail.aliases);
    }
  }, [detail]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!vendorId) return;

      // Update core vendor fields
      await api.patch(`/vendors/${vendorId}`, {
        name: form.name.trim(),
        tax_id: form.tax_id.trim() || null,
        payment_terms: form.payment_terms,
        is_active: form.is_active,
      });

      // Reconcile aliases: delete removed ones, add new ones
      const newAliasNames = form.aliases
        .split(",")
        .map((a) => a.trim())
        .filter(Boolean);
      const originalNames = originalAliases.map((a) => a.alias);

      // Delete aliases no longer present
      for (const orig of originalAliases) {
        if (!newAliasNames.includes(orig.alias)) {
          await api.delete(`/vendors/${vendorId}/aliases/${orig.id}`);
        }
      }

      // Add new aliases not previously present
      for (const name of newAliasNames) {
        if (!originalNames.includes(name)) {
          await api.post(`/vendors/${vendorId}/aliases`, { alias_name: name });
        }
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-vendors"] });
      queryClient.invalidateQueries({ queryKey: ["vendor-detail", vendorId] });
      onSuccess("Vendor updated successfully");
      onClose();
    },
    onError: (err) => onError(extractApiError(err)),
  });

  return (
    <Dialog open={!!vendorId} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit Vendor</DialogTitle>
        </DialogHeader>
        {isLoading ? (
          <div className="py-8 text-center text-gray-400 text-sm">
            Loading…
          </div>
        ) : detail ? (
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="ev-name">
                Name <span className="text-red-500">*</span>
              </Label>
              <Input
                id="ev-name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ev-aliases">
                Aliases{" "}
                <span className="text-gray-400 font-normal text-xs">
                  (comma-separated)
                </span>
              </Label>
              <Input
                id="ev-aliases"
                placeholder="Acme, ACME Corporation"
                value={form.aliases}
                onChange={(e) =>
                  setForm({ ...form, aliases: e.target.value })
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label>Payment Terms</Label>
              <Select
                value={String(form.payment_terms)}
                onValueChange={(v) =>
                  setForm({ ...form, payment_terms: Number(v) })
                }
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
              <Label htmlFor="ev-tax-id">Tax ID</Label>
              <Input
                id="ev-tax-id"
                placeholder="12-3456789"
                value={form.tax_id}
                onChange={(e) =>
                  setForm({ ...form, tax_id: e.target.value })
                }
              />
            </div>
            <div className="flex items-center gap-3">
              <Label>Active</Label>
              <button
                type="button"
                role="switch"
                aria-checked={form.is_active}
                onClick={() =>
                  setForm({ ...form, is_active: !form.is_active })
                }
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
                  form.is_active ? "bg-green-500" : "bg-gray-300"
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    form.is_active ? "translate-x-6" : "translate-x-1"
                  }`}
                />
              </button>
              <span className="text-sm text-gray-600">
                {form.is_active ? "Active" : "Inactive"}
              </span>
            </div>
          </div>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!form.name.trim() || mutation.isPending || isLoading}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Page ───

export default function AdminVendorsPage() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [editVendorId, setEditVendorId] = useState<string | null>(null);
  const { toast, showToast } = useToast();

  // Debounce search input
  const debounceRef = useRef(
    (() => {
      let timer: ReturnType<typeof setTimeout>;
      return (value: string) => {
        clearTimeout(timer);
        timer = setTimeout(() => {
          setDebouncedSearch(value);
          setPage(1);
        }, 300);
      };
    })()
  ).current;

  const handleSearchChange = (value: string) => {
    setSearch(value);
    debounceRef(value);
  };

  const { data, isLoading } = useQuery<VendorListResponse>({
    queryKey: ["admin-vendors", page, debouncedSearch],
    queryFn: () => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: "20",
      });
      if (debouncedSearch) params.set("name", debouncedSearch);
      return api.get<VendorListResponse>(`/vendors?${params}`).then((r) => r.data);
    },
  });

  const vendors = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / 20) || 1;

  return (
    <div className="space-y-4">
      <ToastBanner toast={toast} />

      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-900">Vendors</h2>
        <Button onClick={() => setCreateOpen(true)}>Add Vendor</Button>
      </div>

      <div className="flex items-center gap-3">
        <Input
          placeholder="Search by name…"
          value={search}
          onChange={(e) => handleSearchChange(e.target.value)}
          className="max-w-xs"
        />
        {debouncedSearch && (
          <span className="text-sm text-gray-500">
            {total} result{total !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Tax ID</TableHead>
                <TableHead>Payment Terms</TableHead>
                <TableHead>Currency</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Invoices</TableHead>
                <TableHead className="w-20" />
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
              {!isLoading && vendors.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={7}
                    className="text-center text-gray-400 py-8"
                  >
                    {debouncedSearch
                      ? `No vendors matching "${debouncedSearch}".`
                      : "No vendors yet. Click Add Vendor to create one."}
                  </TableCell>
                </TableRow>
              )}
              {vendors.map((v) => (
                <TableRow key={v.id} className="cursor-pointer hover:bg-gray-50" onClick={() => setEditVendorId(v.id)}>
                  <TableCell className="font-medium">
                    <Link
                      href={`/admin/vendors/${v.id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="hover:underline text-blue-600"
                    >
                      {v.name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-sm text-gray-500">
                    {v.tax_id ?? <span className="text-gray-300">—</span>}
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-700">
                      {paymentTermsLabel(v.payment_terms)}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm">{v.currency}</TableCell>
                  <TableCell>
                    <StatusBadge active={v.is_active} />
                  </TableCell>
                  <TableCell className="text-sm text-gray-500">
                    {v.invoice_count}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      <Link href={`/admin/vendors/${v.id}`} onClick={(e) => e.stopPropagation()}>
                        <Button size="sm" variant="ghost">
                          View
                        </Button>
                      </Link>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditVendorId(v.id);
                        }}
                      >
                        Edit
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-gray-600">
          <span>{total} total vendors</span>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <span>
              Page {page} of {totalPages}
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      <CreateVendorDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSuccess={(msg) => showToast(msg, "success")}
        onError={(msg) => showToast(msg, "error")}
      />
      <EditVendorDialog
        vendorId={editVendorId}
        onClose={() => setEditVendorId(null)}
        onSuccess={(msg) => showToast(msg, "success")}
        onError={(msg) => showToast(msg, "error")}
      />
    </div>
  );
}
