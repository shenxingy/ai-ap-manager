"use client";

import { useCallback, useRef, useState } from "react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetFooter,
} from "@/components/ui/sheet";
import { format } from "date-fns";
import api from "@/lib/api";

// ─── Types ───

type RuleStatus = "draft" | "in_review" | "published" | "rejected" | "superseded";

interface RuleVersion {
  id: string;
  rule_id: string;
  version_number: number;
  status: RuleStatus;
  config_json: string;
  change_summary: string | null;
  source: "manual" | "policy_upload";
  ai_extracted: boolean;
  created_at: string;
  rule_name?: string;
}

interface RuleListResponse {
  items: RuleVersion[];
  total: number;
}

interface RuleConfig {
  tolerance_pct?: number;
  max_line_variance?: number;
  auto_approve_threshold?: number;
  notes?: string;
  [key: string]: unknown;
}

// ─── Helpers ───

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

// ─── Status Badge ───

const STATUS_STYLES: Record<RuleStatus, string> = {
  draft: "bg-yellow-100 text-yellow-700",
  in_review: "bg-blue-100 text-blue-700",
  published: "bg-green-100 text-green-700",
  rejected: "bg-red-100 text-red-700",
  superseded: "bg-gray-100 text-gray-500",
};

const STATUS_LABELS: Record<RuleStatus, string> = {
  draft: "Draft",
  in_review: "In Review",
  published: "Published",
  rejected: "Rejected",
  superseded: "Superseded",
};

function StatusBadge({ status }: { status: RuleStatus }) {
  const cls = STATUS_STYLES[status] ?? "bg-gray-100 text-gray-500";
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cls}`}
    >
      {STATUS_LABELS[status] ?? status}
      {status === "draft" && (
        <svg
          className="ml-1.5 h-3 w-3 animate-spin text-yellow-600"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8v8H4z"
          />
        </svg>
      )}
    </span>
  );
}

// ─── Upload Zone ───

interface UploadZoneProps {
  onUploadSuccess: () => void;
  onError: (msg: string) => void;
}

function UploadZone({ onUploadSuccess, onError }: UploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      const allowed = ["application/pdf", "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain"];
      if (!allowed.includes(file.type) && !file.name.match(/\.(pdf|doc|docx|txt)$/i)) {
        onError("Only PDF, DOC, DOCX, and TXT files are supported");
        return;
      }
      setIsUploading(true);
      try {
        const form = new FormData();
        form.append("file", file);
        await api.post("/rules/upload-policy", form, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        onUploadSuccess();
      } catch (err) {
        onError(extractApiError(err));
      } finally {
        setIsUploading(false);
      }
    },
    [onUploadSuccess, onError]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={onDrop}
      onClick={() => fileRef.current?.click()}
      className={`cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
        isDragging
          ? "border-blue-400 bg-blue-50"
          : "border-gray-300 bg-gray-50 hover:border-gray-400 hover:bg-gray-100"
      }`}
    >
      <input
        ref={fileRef}
        type="file"
        className="hidden"
        accept=".pdf,.doc,.docx,.txt"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          e.target.value = "";
        }}
      />
      {isUploading ? (
        <div className="space-y-2">
          <svg
            className="mx-auto h-8 w-8 animate-spin text-blue-500"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <p className="text-sm text-gray-600">Uploading and extracting policy…</p>
        </div>
      ) : (
        <div className="space-y-2">
          <svg className="mx-auto h-10 w-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <p className="text-sm font-medium text-gray-700">
            Drop a policy document here, or click to browse
          </p>
          <p className="text-xs text-gray-400">PDF, DOC, DOCX, TXT</p>
        </div>
      )}
    </div>
  );
}

// ─── Rule Detail Sheet ───

interface RuleSheetProps {
  rule: RuleVersion | null;
  onClose: () => void;
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}

function RuleDetailSheet({ rule, onClose, onSuccess, onError }: RuleSheetProps) {
  const queryClient = useQueryClient();
  const [config, setConfig] = useState<RuleConfig>({});

  // Parse config_json when rule changes
  const parsedConfig: RuleConfig = (() => {
    if (!rule) return {};
    try {
      return JSON.parse(rule.config_json) as RuleConfig;
    } catch {
      return {};
    }
  })();

  const effectiveConfig = Object.keys(config).length > 0 ? config : parsedConfig;

  const publishMutation = useMutation({
    mutationFn: () =>
      api.post(`/rules/${rule!.id}/publish`).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-rules"] });
      onSuccess("Rule published successfully");
      onClose();
    },
    onError: (err) => onError(extractApiError(err)),
  });

  const rejectMutation = useMutation({
    mutationFn: () =>
      api.post(`/rules/${rule!.id}/reject`).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-rules"] });
      onSuccess("Rule rejected");
      onClose();
    },
    onError: (err) => onError(extractApiError(err)),
  });

  const updateField = (key: string, value: string) => {
    const num = parseFloat(value);
    setConfig((prev) => ({
      ...prev,
      [key]: isNaN(num) ? value : num,
    }));
  };

  return (
    <Sheet open={!!rule} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-lg overflow-y-auto">
        <SheetHeader>
          <SheetTitle>
            {rule?.rule_name ?? `Rule v${rule?.version_number}`}
          </SheetTitle>
          {rule && (
            <div className="flex items-center gap-2 pt-1">
              <StatusBadge status={rule.status} />
              {rule.ai_extracted && (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700">
                  AI Extracted
                </span>
              )}
              <span className="text-xs text-gray-400">
                {rule.source === "policy_upload" ? "Policy Upload" : "Manual"}
              </span>
            </div>
          )}
        </SheetHeader>

        {rule && (
          <div className="mt-6 space-y-5">
            <div className="space-y-3">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                Configuration
              </p>

              <div className="space-y-1.5">
                <Label htmlFor="cfg-tolerance">Tolerance % (matching)</Label>
                <Input
                  id="cfg-tolerance"
                  type="number"
                  step="0.1"
                  placeholder="e.g. 2.5"
                  value={effectiveConfig.tolerance_pct ?? ""}
                  onChange={(e) => updateField("tolerance_pct", e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="cfg-variance">Max Line Variance</Label>
                <Input
                  id="cfg-variance"
                  type="number"
                  step="0.01"
                  placeholder="e.g. 10.00"
                  value={effectiveConfig.max_line_variance ?? ""}
                  onChange={(e) => updateField("max_line_variance", e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="cfg-threshold">Auto-Approve Threshold</Label>
                <Input
                  id="cfg-threshold"
                  type="number"
                  step="0.01"
                  placeholder="e.g. 500.00"
                  value={effectiveConfig.auto_approve_threshold ?? ""}
                  onChange={(e) => updateField("auto_approve_threshold", e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="cfg-notes">Notes</Label>
                <Input
                  id="cfg-notes"
                  placeholder="Optional notes"
                  value={(effectiveConfig.notes as string) ?? ""}
                  onChange={(e) => updateField("notes", e.target.value)}
                />
              </div>
            </div>

            {rule.change_summary && (
              <div className="space-y-1.5">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Change Summary
                </p>
                <p className="text-sm text-gray-700 bg-gray-50 rounded p-3">
                  {rule.change_summary}
                </p>
              </div>
            )}

            <div className="text-xs text-gray-400">
              Created {format(new Date(rule.created_at), "MMM d, yyyy HH:mm")}
            </div>
          </div>
        )}

        {rule && (
          <SheetFooter className="mt-8 gap-2">
            <Button
              variant="outline"
              onClick={() => rejectMutation.mutate()}
              disabled={
                rejectMutation.isPending ||
                publishMutation.isPending ||
                rule.status === "rejected" ||
                rule.status === "published"
              }
              className="text-red-600 border-red-200 hover:bg-red-50"
            >
              {rejectMutation.isPending ? "Rejecting…" : "Reject"}
            </Button>
            <Button
              onClick={() => publishMutation.mutate()}
              disabled={
                publishMutation.isPending ||
                rejectMutation.isPending ||
                rule.status === "published" ||
                rule.status === "rejected"
              }
            >
              {publishMutation.isPending ? "Publishing…" : "Approve & Publish"}
            </Button>
          </SheetFooter>
        )}
      </SheetContent>
    </Sheet>
  );
}

// ─── Page ───

export default function AdminRulesPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [selectedRule, setSelectedRule] = useState<RuleVersion | null>(null);
  const { toast, showToast } = useToast();

  const { data, isLoading } = useQuery<RuleListResponse>({
    queryKey: ["admin-rules", page],
    queryFn: () =>
      api
        .get(`/rules?skip=${(page - 1) * 20}&limit=20`)
        .then((r) => r.data),
    retry: false,
  });

  const rules = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / 20) || 1;

  return (
    <div className="space-y-5">
      <ToastBanner toast={toast} />

      <div>
        <h2 className="text-2xl font-bold text-gray-900">Policy Rules</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Upload policy documents to extract rules, or review AI-generated rule versions
        </p>
      </div>

      <UploadZone
        onUploadSuccess={() => {
          showToast("Policy uploaded — processing started", "success");
          queryClient.invalidateQueries({ queryKey: ["admin-rules"] });
        }}
        onError={(msg) => showToast(msg, "error")}
      />

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Rule</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="w-20" />
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
              {!isLoading && rules.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-gray-400 py-8">
                    No rules yet. Upload a policy document to get started.
                  </TableCell>
                </TableRow>
              )}
              {rules.map((rule) => (
                <TableRow
                  key={rule.id}
                  className="cursor-pointer hover:bg-gray-50"
                  onClick={() => setSelectedRule(rule)}
                >
                  <TableCell className="font-medium">
                    {rule.rule_name ?? `Rule ${rule.rule_id.slice(0, 8)}`}
                  </TableCell>
                  <TableCell className="text-sm text-gray-500">
                    v{rule.version_number}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={rule.status} />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm text-gray-600">
                        {rule.source === "policy_upload" ? "Policy Upload" : "Manual"}
                      </span>
                      {rule.ai_extracted && (
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-600">
                          AI
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm text-gray-500">
                    {format(new Date(rule.created_at), "MMM d, yyyy")}
                  </TableCell>
                  <TableCell>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedRule(rule);
                      }}
                    >
                      Review
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-gray-600">
          <span>{total} total rules</span>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <span>Page {page} of {totalPages}</span>
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

      <RuleDetailSheet
        rule={selectedRule}
        onClose={() => setSelectedRule(null)}
        onSuccess={(msg) => showToast(msg, "success")}
        onError={(msg) => showToast(msg, "error")}
      />
    </div>
  );
}
