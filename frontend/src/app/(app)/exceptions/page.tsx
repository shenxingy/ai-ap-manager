"use client";

import { useState, useEffect, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { format } from "date-fns";
import api from "@/lib/api";
import Link from "next/link";

// ─── Types ───

interface Exception {
  id: string;
  code: string;
  severity: string;
  status: string;
  description: string;
  assigned_to: string | null;
  assigned_to_email: string | null;
  resolution_notes: string | null;
  invoice_id: string;
  invoice_number: string | null;
  created_at: string;
}

interface ExceptionListResponse {
  items: Exception[];
  total: number;
  page: number;
  page_size: number;
}

interface AdminUser {
  id: string;
  name: string;
  email: string;
}

interface Comment {
  id: string;
  author: string;
  body: string;
  created_at: string;
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

// ─── Filter Bar ───

const STATUS_OPTIONS = ["OPEN", "IN_PROGRESS", "RESOLVED", "WAIVED"];
const SEVERITY_OPTIONS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

interface FilterBarProps {
  statuses: string[];
  code: string;
  severity: string;
  assignedTo: string;
  onStatusChange: (s: string[]) => void;
  onCodeChange: (s: string) => void;
  onSeverityChange: (s: string) => void;
  onAssignedToChange: (s: string) => void;
}

function FilterBar({
  statuses,
  code,
  severity,
  assignedTo,
  onStatusChange,
  onCodeChange,
  onSeverityChange,
  onAssignedToChange,
}: FilterBarProps) {
  const [codeInput, setCodeInput] = useState(code);
  const [assignedInput, setAssignedInput] = useState(assignedTo);

  // Keep callbacks in refs so debounce effects don't go stale
  const onCodeRef = useRef(onCodeChange);
  const onAssignedRef = useRef(onAssignedToChange);
  useEffect(() => { onCodeRef.current = onCodeChange; });
  useEffect(() => { onAssignedRef.current = onAssignedToChange; });

  // Sync local inputs when parent clears filters
  useEffect(() => { setCodeInput(code); }, [code]);
  useEffect(() => { setAssignedInput(assignedTo); }, [assignedTo]);

  // Debounce code input 300ms — skip initial mount
  const codeMount = useRef(true);
  useEffect(() => {
    if (codeMount.current) { codeMount.current = false; return; }
    const t = setTimeout(() => onCodeRef.current(codeInput), 300);
    return () => clearTimeout(t);
  }, [codeInput]);

  // Debounce assigned_to input 300ms — skip initial mount
  const assignedMount = useRef(true);
  useEffect(() => {
    if (assignedMount.current) { assignedMount.current = false; return; }
    const t = setTimeout(() => onAssignedRef.current(assignedInput), 300);
    return () => clearTimeout(t);
  }, [assignedInput]);

  const toggleStatus = (s: string) =>
    onStatusChange(
      statuses.includes(s) ? statuses.filter((x) => x !== s) : [...statuses, s]
    );

  const hasFilters = statuses.length > 0 || severity || code || assignedTo;

  return (
    <div className="flex flex-wrap items-center gap-3 p-3 bg-gray-50 rounded-lg border">
      {/* Status multi-select */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-xs font-medium text-gray-600 whitespace-nowrap">Status:</span>
        {STATUS_OPTIONS.map((s) => (
          <button
            key={s}
            onClick={() => toggleStatus(s)}
            className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
              statuses.includes(s)
                ? "bg-blue-600 text-white"
                : "bg-white text-gray-600 border hover:bg-gray-100"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Severity filter */}
      <div className="flex items-center gap-1.5">
        <span className="text-xs font-medium text-gray-600">Severity:</span>
        <select
          value={severity}
          onChange={(e) => onSeverityChange(e.target.value)}
          className="text-xs border rounded px-2 bg-white text-gray-700 h-7"
        >
          <option value="">All</option>
          {SEVERITY_OPTIONS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      {/* Code filter */}
      <div className="flex items-center gap-1.5">
        <span className="text-xs font-medium text-gray-600">Code:</span>
        <Input
          placeholder="Filter by code…"
          className="h-7 text-xs w-36"
          value={codeInput}
          onChange={(e) => setCodeInput(e.target.value)}
        />
      </div>

      {/* Assigned-to filter */}
      <div className="flex items-center gap-1.5">
        <span className="text-xs font-medium text-gray-600 whitespace-nowrap">Assigned to:</span>
        <Input
          placeholder="Filter by user…"
          className="h-7 text-xs w-36"
          value={assignedInput}
          onChange={(e) => setAssignedInput(e.target.value)}
        />
      </div>

      {hasFilters && (
        <button
          onClick={() => {
            onStatusChange([]);
            onSeverityChange("");
            onCodeChange("");
            onAssignedToChange("");
          }}
          className="text-xs text-gray-500 hover:text-gray-800 ml-auto"
        >
          Clear filters
        </button>
      )}
    </div>
  );
}

// ─── Exception Detail Sheet ───

function ExceptionSheet({
  exception,
  onClose,
  showToast,
}: {
  exception: Exception | null;
  onClose: () => void;
  showToast: (msg: string, type: "success" | "error") => void;
}) {
  const queryClient = useQueryClient();
  const [comment, setComment] = useState("");
  const [newStatus, setNewStatus] = useState<string | null>(null);
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [selectedUser, setSelectedUser] = useState("");

  // Reset local state whenever a different exception is opened
  useEffect(() => {
    if (exception) {
      setNewStatus(null);
      setResolutionNotes(exception.resolution_notes ?? "");
      setSelectedUser(exception.assigned_to ?? "");
      setComment("");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exception?.id]);

  const { data: comments = [] } = useQuery<Comment[]>({
    queryKey: ["exception-comments", exception?.id],
    queryFn: () =>
      api.get(`/exceptions/${exception!.id}/comments`).then((r) => r.data),
    enabled: !!exception,
  });

  const { data: usersData } = useQuery<{ items: AdminUser[] }>({
    queryKey: ["admin-users-list"],
    queryFn: () =>
      api.get("/admin/users?page=1&page_size=100").then((r) => r.data),
    enabled: !!exception,
  });

  const users = usersData?.items ?? [];

  const submitComment = useMutation({
    mutationFn: (body: string) =>
      api.post(`/exceptions/${exception!.id}/comments`, { body }),
    onSuccess: () => {
      setComment("");
      queryClient.invalidateQueries({
        queryKey: ["exception-comments", exception?.id],
      });
    },
  });

  const saveChanges = useMutation({
    mutationFn: () =>
      api.patch(`/exceptions/${exception!.id}`, {
        status: newStatus ?? exception!.status,
        resolution_notes: resolutionNotes || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["exceptions"] });
      showToast("Changes saved", "success");
      setNewStatus(null);
    },
    onError: () => showToast("Failed to save changes", "error"),
  });

  const assignTo = useMutation({
    mutationFn: (userId: string) =>
      api.patch(`/exceptions/${exception!.id}`, {
        assigned_to: userId || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["exceptions"] });
      showToast("Assigned successfully", "success");
    },
    onError: () => showToast("Failed to assign", "error"),
  });

  const hasChanges =
    (newStatus !== null && newStatus !== exception?.status) ||
    resolutionNotes !== (exception?.resolution_notes ?? "");

  return (
    <Sheet open={!!exception} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-[480px] sm:w-[540px] flex flex-col gap-0">
        {exception && (
          <>
            <SheetHeader className="pb-4">
              <SheetTitle className="font-mono text-sm">{exception.code}</SheetTitle>
            </SheetHeader>

            <div className="space-y-4 text-sm overflow-y-auto flex-shrink-0 pb-4">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge
                  variant={
                    exception.severity === "HIGH" || exception.severity === "CRITICAL"
                      ? "destructive"
                      : "secondary"
                  }
                >
                  {exception.severity}
                </Badge>
                <Badge variant="outline">{exception.status}</Badge>
                <Link
                  href={`/invoices/${exception.invoice_id}`}
                  className="text-blue-600 hover:underline"
                >
                  Invoice {exception.invoice_number || exception.invoice_id.slice(0, 8)}
                </Link>
              </div>
              <p className="text-gray-600">{exception.description}</p>

              {/* Assigned To */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-600">Assigned To</label>
                <select
                  value={selectedUser}
                  onChange={(e) => {
                    setSelectedUser(e.target.value);
                    assignTo.mutate(e.target.value);
                  }}
                  className="w-full border rounded-md px-3 py-1.5 text-sm bg-white text-gray-700"
                >
                  <option value="">Unassigned</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name} ({u.email})
                    </option>
                  ))}
                </select>
              </div>

              {/* Status */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-600">Status</label>
                <Select
                  value={newStatus ?? exception.status}
                  onValueChange={(v) => setNewStatus(v)}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {["OPEN", "IN_PROGRESS", "RESOLVED", "WAIVED"].map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Resolution Notes */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-600">Resolution Notes</label>
                <textarea
                  className="w-full border rounded-md px-3 py-2 text-sm resize-none"
                  rows={3}
                  placeholder="Add resolution notes…"
                  value={resolutionNotes}
                  onChange={(e) => setResolutionNotes(e.target.value)}
                />
              </div>

              <Button
                size="sm"
                disabled={!hasChanges || saveChanges.isPending}
                onClick={() => saveChanges.mutate()}
                className="w-full"
              >
                {saveChanges.isPending ? "Saving…" : "Save Changes"}
              </Button>
            </div>

            {/* Comments */}
            <div className="flex-1 flex flex-col min-h-0 border-t pt-4">
              <h4 className="text-sm font-semibold mb-3">Comments</h4>
              <div className="flex-1 overflow-y-auto space-y-3 pr-1">
                {comments.map((c) => (
                  <div key={c.id} className="bg-gray-50 rounded-lg px-3 py-2">
                    <p className="text-xs text-gray-500 mb-1">
                      {c.author} · {format(new Date(c.created_at), "MMM d, HH:mm")}
                    </p>
                    <p className="text-sm">{c.body}</p>
                  </div>
                ))}
                {comments.length === 0 && (
                  <p className="text-sm text-gray-400">No comments yet.</p>
                )}
              </div>
              <div className="mt-3 flex gap-2">
                <textarea
                  className="flex-1 border rounded-md px-3 py-2 text-sm resize-none"
                  rows={2}
                  placeholder="Add a comment…"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                />
                <Button
                  size="sm"
                  disabled={!comment.trim()}
                  onClick={() => submitComment.mutate(comment)}
                >
                  Post
                </Button>
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

// ─── Exceptions Content (uses useSearchParams) ───

function ExceptionsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { toast, showToast } = useToast();
  const [selected, setSelected] = useState<Exception | null>(null);

  // Read filters from URL search params
  const urlStatuses = searchParams.getAll("status");
  const urlCode = searchParams.get("code") ?? "";
  const urlSeverity = searchParams.get("severity") ?? "";
  const urlAssignedTo = searchParams.get("assigned_to") ?? "";
  const urlPage = Math.max(1, parseInt(searchParams.get("page") ?? "1", 10));

  // Update URL params — reads window.location.search for stability
  const updateParams = (updates: Record<string, string | string[]>) => {
    const params = new URLSearchParams(window.location.search);
    Object.entries(updates).forEach(([key, value]) => {
      params.delete(key);
      if (Array.isArray(value)) {
        value.forEach((v) => params.append(key, v));
      } else if (value !== "") {
        params.set(key, value);
      }
    });
    params.set("page", "1"); // reset to page 1 on filter change
    router.replace(`?${params.toString()}`);
  };

  const setPage = (p: number) => {
    const params = new URLSearchParams(window.location.search);
    params.set("page", String(p));
    router.replace(`?${params.toString()}`);
  };

  // Build API query string from current URL filters
  const buildQuery = () => {
    const q = new URLSearchParams();
    if (urlStatuses.length > 0) {
      q.set("status", urlStatuses[0]); // backend accepts single status
    }
    if (urlCode) q.set("exception_code", urlCode);
    if (urlSeverity) q.set("severity", urlSeverity);
    q.set("page", String(urlPage));
    q.set("page_size", "20");
    return q.toString();
  };

  const { data, isLoading } = useQuery<ExceptionListResponse>({
    queryKey: ["exceptions", urlStatuses, urlCode, urlSeverity, urlAssignedTo, urlPage],
    queryFn: () => api.get(`/exceptions?${buildQuery()}`).then((r) => r.data),
  });

  const exceptions = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / 20) || 1;

  return (
    <div className="space-y-4">
      <ToastBanner toast={toast} />

      <h2 className="text-2xl font-bold text-gray-900">Exceptions</h2>

      <FilterBar
        statuses={urlStatuses}
        code={urlCode}
        severity={urlSeverity}
        assignedTo={urlAssignedTo}
        onStatusChange={(s) => updateParams({ status: s })}
        onCodeChange={(s) => updateParams({ code: s })}
        onSeverityChange={(s) => updateParams({ severity: s })}
        onAssignedToChange={(s) => updateParams({ assigned_to: s })}
      />

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead>
                <TableHead>Severity</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Assigned To</TableHead>
                <TableHead>Invoice</TableHead>
                <TableHead>Raised At</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-gray-400 py-8">
                    Loading…
                  </TableCell>
                </TableRow>
              )}
              {!isLoading && exceptions.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-gray-400 py-8">
                    No exceptions found.
                  </TableCell>
                </TableRow>
              )}
              {exceptions.map((ex) => (
                <TableRow
                  key={ex.id}
                  className="cursor-pointer hover:bg-gray-50"
                  onClick={() => setSelected(ex)}
                >
                  <TableCell className="font-mono text-xs">{ex.code}</TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        ex.severity === "HIGH" || ex.severity === "CRITICAL"
                          ? "destructive"
                          : "secondary"
                      }
                    >
                      {ex.severity}
                    </Badge>
                  </TableCell>
                  <TableCell>{ex.status}</TableCell>
                  <TableCell>{ex.assigned_to_email || "—"}</TableCell>
                  <TableCell>
                    <Link
                      href={`/invoices/${ex.invoice_id}`}
                      className="text-blue-600 hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {ex.invoice_number || ex.invoice_id.slice(0, 8)}
                    </Link>
                  </TableCell>
                  <TableCell className="text-sm text-gray-500">
                    {format(new Date(ex.created_at), "MMM d, yyyy")}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Pagination */}
      <div className="flex items-center justify-between text-sm text-gray-600">
        <span>{total} total exceptions</span>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={urlPage <= 1}
            onClick={() => setPage(urlPage - 1)}
          >
            Previous
          </Button>
          <span>Page {urlPage} of {totalPages}</span>
          <Button
            size="sm"
            variant="outline"
            disabled={urlPage >= totalPages}
            onClick={() => setPage(urlPage + 1)}
          >
            Next
          </Button>
        </div>
      </div>

      <ExceptionSheet
        exception={selected}
        onClose={() => setSelected(null)}
        showToast={showToast}
      />
    </div>
  );
}

// ─── Page ───

export default function ExceptionsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-gray-400">Loading…</div>}>
      <ExceptionsContent />
    </Suspense>
  );
}
