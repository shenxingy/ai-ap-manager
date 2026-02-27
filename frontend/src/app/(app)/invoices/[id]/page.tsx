"use client";

import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { format } from "date-fns";
import api from "@/lib/api";

// ─── Types ───

interface ExtractedField {
  value: string | null;
  confidence: number | null;
  is_overridden?: boolean;
}

interface ExtractionResult {
  pass_number: 1 | 2;
  extracted_fields: Record<string, unknown>;
  discrepancy_fields: string[];
}

interface Invoice {
  id: string;
  invoice_number: string;
  vendor_name_raw: string;
  total_amount: number;
  status: string;
  fraud_score: number | null;
  invoice_date: string | null;
  due_date: string | null;
  currency: string;
  created_at: string;
  confidence_score?: number | null;
  extracted_fields?: Record<string, ExtractedField>;
  extraction_results?: ExtractionResult[];
}

interface LineItem {
  id: string;
  description: string;
  quantity: number;
  unit_price: number;
  total_price: number;
  gl_code: string | null;
  gl_suggestion: string | null;
  gl_suggestion_confidence?: number | null;
  cost_center?: string | null;
}

interface GRLineOut {
  id: string;
  line_number: number;
  description: string;
  qty_received: number;
  unit: string | null;
}

interface GRNSummaryOut {
  id: string;
  gr_number: string;
  received_at: string;
  lines: GRLineOut[];
}

interface LineItemMatchOut {
  id: string;
  match_result_id: string;
  invoice_line_id: string;
  po_line_id: string | null;
  gr_line_id: string | null;
  status: string; // matched, qty_variance, price_variance, unmatched
  qty_variance: number | null;
  price_variance: number | null;
  price_variance_pct: number | null;
  created_at: string;
  // Enriched fields
  description: string | null;
  invoice_amount: number | null;
  po_amount: number | null;
  qty_invoiced: number | null;
  qty_on_po: number | null;
  qty_received: number | null;
  exception_code: string | null;
  grn_lines_used: string[] | null;
}

interface MatchResult {
  id: string;
  match_type: string; // 2way, 3way, non_po
  match_status: string;
  po_id: string | null;
  gr_id: string | null;
  amount_variance: number | null;
  amount_variance_pct: number | null;
  matched_at: string | null;
  notes: string | null;
  line_matches: LineItemMatchOut[];
  // Enriched
  po_number: string | null;
  gr_number: string | null;
  grn_data: GRNSummaryOut | null;
}

interface ExceptionItem {
  id: string;
  code: string;
  severity: string;
  status: string;
  description: string;
  created_at: string;
}

interface ApprovalTask {
  id: string;
  status: string;
  assignee_name: string;
  assigned_at: string;
  decided_at: string | null;
  notes: string | null;
}

interface AuditEntry {
  id: string;
  action: string;
  actor: string;
  created_at: string;
  detail: string | null;
}

// ─── Helper Components ───

function ConfidenceDot({ score }: { score: number | null | undefined }) {
  if (score == null)
    return <span className="inline-block w-2 h-2 rounded-full bg-gray-300 ml-1.5" title="No confidence data" />;
  if (score >= 0.9)
    return <span className="inline-block w-2 h-2 rounded-full bg-green-500 ml-1.5" title={`${(score * 100).toFixed(0)}% confidence`} />;
  if (score >= 0.6)
    return <span className="inline-block w-2 h-2 rounded-full bg-yellow-400 ml-1.5" title={`${(score * 100).toFixed(0)}% confidence`} />;
  return <span className="inline-block w-2 h-2 rounded-full bg-red-500 ml-1.5" title={`${(score * 100).toFixed(0)}% confidence`} />;
}

function GlConfBadge({ score }: { score: number | null | undefined }) {
  if (score == null) return null;
  const pct = `${(score * 100).toFixed(0)}%`;
  if (score >= 0.9) return <span className="text-xs bg-green-100 text-green-700 px-1 py-0.5 rounded">{pct}</span>;
  if (score >= 0.6) return <span className="text-xs bg-yellow-100 text-yellow-700 px-1 py-0.5 rounded">{pct}</span>;
  return <span className="text-xs bg-red-100 text-red-700 px-1 py-0.5 rounded">{pct}</span>;
}

// ─── Fraud Badge ───

function fraudBadge(score: number | null): string {
  if (score === null) return "N/A";
  if (score >= 0.9) return "🔴🔴 CRITICAL";
  if (score >= 0.7) return "🔴 HIGH";
  if (score >= 0.4) return "🟡 MEDIUM";
  return "🟢 LOW";
}

// ─── Match Row Color ───

function matchLineClass(status: string): string {
  if (status === "matched" || status === "MATCHED")
    return "border-l-4 border-l-green-500 bg-green-50/50";
  if (status === "qty_variance" || status === "price_variance" || status === "WITHIN_TOLERANCE")
    return "border-l-4 border-l-yellow-400 bg-yellow-50/50";
  if (status === "unmatched" || status === "OUT_OF_TOLERANCE")
    return "border-l-4 border-l-red-500 bg-red-50/50";
  return "";
}

function matchStatusLabel(status: string): string {
  if (status === "matched") return "Matched";
  if (status === "qty_variance") return "Qty Variance";
  if (status === "price_variance") return "Price Variance";
  if (status === "unmatched") return "Unmatched";
  return status;
}

function matchStatusClass(status: string): string {
  if (status === "matched") return "text-green-600 font-medium text-xs";
  if (status === "qty_variance" || status === "price_variance") return "text-yellow-600 font-medium text-xs";
  return "text-red-600 font-medium text-xs";
}

function matchTypeBadge(matchType: string): { label: string; cls: string } {
  if (matchType === "3way") return { label: "3-Way Match", cls: "bg-purple-100 text-purple-700 border border-purple-200" };
  if (matchType === "2way") return { label: "2-Way Match", cls: "bg-blue-100 text-blue-700 border border-blue-200" };
  return { label: "Non-PO", cls: "bg-gray-100 text-gray-600 border border-gray-200" };
}

// ─── Page ───

export default function InvoiceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();

  // Action bar state
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  // Field editing state
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [savingField, setSavingField] = useState(false);

  // Extraction comparison state
  const [comparisonOpen, setComparisonOpen] = useState(false);

  // GL editing state
  const [glEdits, setGlEdits] = useState<Record<string, { gl_account: string; cost_center: string }>>({});
  const [savingGl, setSavingGl] = useState<string | null>(null);
  const [confirmedLineIds, setConfirmedLineIds] = useState<Set<string>>(new Set());

  function showToast(message: string, type: "success" | "error") {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3500);
  }

  // ─── Queries ───

  const { data: invoice } = useQuery<Invoice>({
    queryKey: ["invoice", id],
    queryFn: () => api.get(`/invoices/${id}`).then((r) => r.data),
  });

  const { data: lineItems = [] } = useQuery<LineItem[]>({
    queryKey: ["invoice-lines", id],
    queryFn: () => api.get(`/invoices/${id}/line-items`).then((r) => r.data),
  });

  const { data: glSuggestions } = useQuery<Record<string, { gl_account: string; confidence_pct: number }>>({
    queryKey: ["invoice-gl", id],
    queryFn: () =>
      api.get(`/invoices/${id}/gl-suggestions`).then((r) => {
        const map: Record<string, { gl_account: string; confidence_pct: number }> = {};
        (r.data.suggestions ?? []).forEach((s: { line_id: string; gl_account: string; confidence_pct: number }) => {
          map[s.line_id] = { gl_account: s.gl_account, confidence_pct: s.confidence_pct };
        });
        return map;
      }),
  });

  const { data: match } = useQuery<MatchResult>({
    queryKey: ["invoice-match", id],
    queryFn: () => api.get(`/invoices/${id}/match`).then((r) => r.data),
  });

  const { data: exceptions = [] } = useQuery<ExceptionItem[]>({
    queryKey: ["invoice-exceptions", id],
    queryFn: () => api.get(`/invoices/${id}/exceptions`).then((r) => r.data),
  });

  const { data: approvals = [] } = useQuery<ApprovalTask[]>({
    queryKey: ["invoice-approvals", id],
    queryFn: () => api.get(`/invoices/${id}/approvals`).then((r) => r.data),
  });

  const { data: auditLog = [] } = useQuery<AuditEntry[]>({
    queryKey: ["invoice-audit", id],
    queryFn: () => api.get(`/invoices/${id}/audit`).then((r) => r.data),
  });

  // ─── Action Handlers ───

  async function handleRerunExtraction() {
    setLoadingAction("extract");
    try {
      await api.post(`/invoices/${id}/extract`);
      await queryClient.invalidateQueries({ queryKey: ["invoice", id] });
      showToast("Extraction re-queued", "success");
    } catch {
      showToast("Failed to re-run extraction", "error");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleRetriggerMatch() {
    setLoadingAction("match");
    try {
      await api.post(`/invoices/${id}/match`);
      await queryClient.invalidateQueries({ queryKey: ["invoice-match", id] });
      showToast("Re-match triggered", "success");
    } catch {
      showToast("Failed to trigger re-match", "error");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleRerun3WayMatch() {
    setLoadingAction("match3way");
    try {
      await api.post(`/invoices/${id}/match`, null, { params: { match_type: "3way" } });
      await queryClient.invalidateQueries({ queryKey: ["invoice-match", id] });
      await queryClient.invalidateQueries({ queryKey: ["invoice", id] });
      showToast("3-Way match complete", "success");
    } catch {
      showToast("Failed to run 3-way match", "error");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleDownload() {
    setLoadingAction("download");
    try {
      const response = await api.get(`/invoices/${id}/download`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `invoice-${invoice?.invoice_number || id}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      showToast("Download started", "success");
    } catch {
      showToast("Download failed", "error");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleSaveField(fieldName: string, value: string) {
    setSavingField(true);
    try {
      await api.patch(`/invoices/${id}/fields`, { field_name: fieldName, corrected_value: value });
      await queryClient.invalidateQueries({ queryKey: ["invoice", id] });
      setEditingField(null);
      showToast("Field updated", "success");
    } catch {
      showToast("Failed to save field", "error");
    } finally {
      setSavingField(false);
    }
  }

  async function handleConfirmGl(lineId: string) {
    const edit = glEdits[lineId];
    if (!edit?.gl_account) return;
    setSavingGl(lineId);
    try {
      await api.put(`/invoices/${id}/lines/${lineId}/gl`, edit);
      await queryClient.invalidateQueries({ queryKey: ["invoice-lines", id] });
      setConfirmedLineIds((prev) => { const next = new Set(prev); next.add(lineId); return next; });
      showToast("GL code confirmed", "success");
    } catch {
      showToast("Failed to save GL code", "error");
    } finally {
      setSavingGl(null);
    }
  }

  async function handleConfirmAllGl() {
    const lineIds = Object.keys(glEdits);
    if (lineIds.length === 0) {
      showToast("No GL codes to confirm", "error");
      return;
    }
    setSavingGl("all");
    try {
      const payload = {
        lines: lineIds.map((lineId) => ({
          line_id: lineId,
          gl_account: glEdits[lineId].gl_account,
          cost_center: glEdits[lineId].cost_center || null,
        })),
      };
      const res = await api.put(`/invoices/${id}/lines/gl-bulk`, payload);
      await queryClient.invalidateQueries({ queryKey: ["invoice-lines", id] });
      setConfirmedLineIds((prev) => { const next = new Set(prev); lineIds.forEach((lid) => next.add(lid)); return next; });
      const { updated, errors } = res.data;
      if (errors === 0) showToast(`All ${updated} GL codes confirmed`, "success");
      else showToast(`${errors} failed, ${updated} saved`, "error");
    } catch {
      showToast("Failed to confirm GL codes", "error");
    } finally {
      setSavingGl(null);
    }
  }

  if (!invoice) {
    return <div className="py-12 text-center text-gray-500">Loading invoice...</div>;
  }

  // ─── Detail Fields Config ───

  const detailFields = [
    {
      label: "Invoice Number",
      value: invoice.invoice_number,
      fieldName: "invoice_number",
      rawValue: invoice.invoice_number,
      editable: true,
      confidence: invoice.extracted_fields?.invoice_number?.confidence ?? invoice.confidence_score,
      isOverridden: !!invoice.extracted_fields?.invoice_number?.is_overridden,
    },
    {
      label: "Vendor",
      value: invoice.vendor_name_raw,
      fieldName: "vendor_name_raw",
      rawValue: invoice.vendor_name_raw,
      editable: true,
      confidence: invoice.extracted_fields?.vendor_name_raw?.confidence ?? invoice.confidence_score,
      isOverridden: !!invoice.extracted_fields?.vendor_name_raw?.is_overridden,
    },
    {
      label: "Amount",
      value: `${invoice.currency} ${invoice.total_amount?.toLocaleString()}`,
      fieldName: "total_amount",
      rawValue: String(invoice.total_amount),
      editable: true,
      confidence: invoice.extracted_fields?.total_amount?.confidence ?? invoice.confidence_score,
      isOverridden: !!invoice.extracted_fields?.total_amount?.is_overridden,
    },
    {
      label: "Status",
      value: invoice.status,
      fieldName: "status",
      rawValue: invoice.status,
      editable: false,
      confidence: undefined as number | null | undefined,
      isOverridden: false,
    },
    {
      label: "Invoice Date",
      value: invoice.invoice_date ? format(new Date(invoice.invoice_date), "MMM d, yyyy") : "—",
      fieldName: "invoice_date",
      rawValue: invoice.invoice_date ?? "",
      editable: true,
      confidence: invoice.extracted_fields?.invoice_date?.confidence ?? invoice.confidence_score,
      isOverridden: !!invoice.extracted_fields?.invoice_date?.is_overridden,
    },
    {
      label: "Due Date",
      value: invoice.due_date ? format(new Date(invoice.due_date), "MMM d, yyyy") : "—",
      fieldName: "due_date",
      rawValue: invoice.due_date ?? "",
      editable: true,
      confidence: invoice.extracted_fields?.due_date?.confidence ?? invoice.confidence_score,
      isOverridden: !!invoice.extracted_fields?.due_date?.is_overridden,
    },
    {
      label: "Received",
      value: format(new Date(invoice.created_at), "MMM d, yyyy HH:mm"),
      fieldName: "created_at",
      rawValue: invoice.created_at,
      editable: false,
      confidence: undefined as number | null | undefined,
      isOverridden: false,
    },
    {
      label: "Fraud Score",
      value: fraudBadge(invoice.fraud_score),
      fieldName: "fraud_score",
      rawValue: String(invoice.fraud_score),
      editable: false,
      confidence: undefined as number | null | undefined,
      isOverridden: false,
    },
  ];

  return (
    <div className="space-y-5">
      {/* Dual Authorization Required — CRITICAL fraud score */}
      {invoice.fraud_score != null && invoice.fraud_score >= 0.9 && (
        <div className="border-l-4 border-l-red-700 bg-red-50 p-4 rounded">
          <p className="text-sm font-semibold text-red-900">⚠️ Dual Authorization Required</p>
          <p className="text-sm text-red-800 mt-1">
            This invoice&apos;s CRITICAL fraud score ({(invoice.fraud_score * 100).toFixed(0)}%) requires 2 ADMIN approvals before payment.
          </p>
        </div>
      )}

      {/* High Fraud Warning (non-critical) */}
      {invoice.fraud_score != null && invoice.fraud_score >= 0.6 && invoice.fraud_score < 0.9 && (
        <div className="border-l-4 border-l-amber-500 bg-amber-50 p-4 rounded">
          <p className="text-sm font-semibold text-amber-800">⚠ Fraud Risk Alert</p>
          <p className="text-sm text-amber-700 mt-1">
            This invoice has a high fraud score ({(invoice.fraud_score * 100).toFixed(0)}%) and requires immediate review before approval.
          </p>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-wrap items-start gap-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">
            Invoice {invoice.invoice_number || invoice.id.slice(0, 8)}
          </h2>
          <p className="text-gray-500 mt-0.5">{invoice.vendor_name_raw}</p>
        </div>
        <div className="flex items-center gap-2 ml-auto flex-wrap">
          <span className="text-xl font-semibold text-gray-700">
            {invoice.currency}{" "}
            {invoice.total_amount?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </span>
          <Badge>{invoice.status}</Badge>
          <Badge variant="outline">{fraudBadge(invoice.fraud_score)}</Badge>
        </div>
      </div>

      {/* Action Bar */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={handleRerunExtraction}
          disabled={loadingAction !== null}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          {loadingAction === "extract" ? (
            <span className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
          ) : (
            <span>⟳</span>
          )}
          Re-run Extraction
        </button>
        <button
          onClick={handleRetriggerMatch}
          disabled={loadingAction !== null}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          {loadingAction === "match" ? (
            <span className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
          ) : (
            <span>⚡</span>
          )}
          Trigger Re-match
        </button>
        <button
          onClick={handleDownload}
          disabled={loadingAction !== null}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          {loadingAction === "download" ? (
            <span className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
          ) : (
            <span>↓</span>
          )}
          Download Original
        </button>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="details">
        <TabsList>
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="lines">Line Items</TabsTrigger>
          <TabsTrigger value="match">Match</TabsTrigger>
          <TabsTrigger value="exceptions">Exceptions</TabsTrigger>
          <TabsTrigger value="approvals">Approvals</TabsTrigger>
          <TabsTrigger value="audit">Audit Log</TabsTrigger>
        </TabsList>

        {/* Details */}
        <TabsContent value="details">
          <Card>
            <CardContent className="pt-4">
              <dl className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
                {detailFields.map((field) => (
                  <div
                    key={field.fieldName}
                    className={`group ${
                      field.isOverridden
                        ? "rounded px-2 py-1 bg-amber-50 border border-amber-200"
                        : ""
                    }`}
                  >
                    <dt className="text-gray-500 flex items-center gap-0.5">
                      {field.label}
                      <ConfidenceDot score={field.confidence} />
                    </dt>
                    <dd className="font-medium mt-0.5 flex items-center gap-2">
                      {editingField === field.fieldName ? (
                        <span className="flex items-center gap-1.5">
                          <input
                            autoFocus
                            className="border border-gray-300 rounded px-2 py-0.5 text-sm w-40 focus:outline-none focus:ring-1 focus:ring-blue-500"
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleSaveField(field.fieldName, editValue);
                              if (e.key === "Escape") setEditingField(null);
                            }}
                          />
                          <button
                            onClick={() => handleSaveField(field.fieldName, editValue)}
                            disabled={savingField}
                            className="text-xs bg-blue-600 text-white px-2 py-0.5 rounded hover:bg-blue-700 disabled:opacity-50"
                          >
                            {savingField ? "…" : "Save"}
                          </button>
                          <button
                            onClick={() => setEditingField(null)}
                            className="text-xs text-gray-400 hover:text-gray-600"
                          >
                            ✕
                          </button>
                        </span>
                      ) : (
                        <>
                          {field.value}
                          {field.editable && (
                            <button
                              onClick={() => {
                                setEditingField(field.fieldName);
                                setEditValue(field.rawValue);
                              }}
                              className="text-gray-400 hover:text-blue-500 opacity-0 group-hover:opacity-100 transition-opacity ml-1"
                              title="Edit field"
                            >
                              ✏
                            </button>
                          )}
                        </>
                      )}
                    </dd>
                  </div>
                ))}
              </dl>

              {/* ─── Extraction Pass Comparison ─── */}
              {(() => {
                const results = invoice.extraction_results ?? [];
                const passA = results.find((r) => r.pass_number === 1);
                const passB = results.find((r) => r.pass_number === 2);
                if (!passA || !passB) return null;
                const discrepancies = Array.from(
                  new Set([...passA.discrepancy_fields, ...passB.discrepancy_fields])
                );
                const hasDiscrepancies = discrepancies.length > 0;
                return (
                  <div className="mt-5 border-t pt-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-gray-700">Extraction Comparison</span>
                      {hasDiscrepancies && (
                        <button
                          onClick={() => setComparisonOpen((o) => !o)}
                          className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1"
                        >
                          {comparisonOpen ? "▲ Hide" : "▼ Show"} {discrepancies.length} discrepant field{discrepancies.length !== 1 ? "s" : ""}
                        </button>
                      )}
                    </div>
                    {!hasDiscrepancies ? (
                      <p className="text-sm text-green-600 flex items-center gap-1">
                        <span>✓</span> Both extraction passes agree
                      </p>
                    ) : comparisonOpen && (
                      <table className="w-full text-xs border-collapse">
                        <thead>
                          <tr className="text-left text-gray-500 border-b">
                            <th className="pb-1.5 pr-3 font-medium w-1/4">Field</th>
                            <th className="pb-1.5 pr-3 font-medium w-[37.5%]">Pass A</th>
                            <th className="pb-1.5 font-medium w-[37.5%]">Pass B</th>
                          </tr>
                        </thead>
                        <tbody>
                          {discrepancies.map((field) => (
                            <tr key={field} className="border-b border-amber-100 last:border-0">
                              <td className="py-1.5 pr-3 font-medium text-gray-600">{field}</td>
                              <td className="py-1.5 pr-3 bg-amber-50 text-amber-900 px-1.5 rounded-l">
                                {String(passA.extracted_fields[field] ?? "—")}
                              </td>
                              <td className="py-1.5 bg-amber-50 text-amber-900 px-1.5 rounded-r">
                                {String(passB.extracted_fields[field] ?? "—")}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                );
              })()}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Line Items */}
        <TabsContent value="lines">
          <Card>
            <CardContent className="p-0">
              {/* Confirm All button */}
              <div className="flex justify-end p-3 border-b">
                <button
                  onClick={handleConfirmAllGl}
                  disabled={savingGl !== null || Object.keys(glEdits).length === 0}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 transition-colors"
                >
                  {savingGl === "all" && (
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  )}
                  Confirm All Coding
                </button>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Description</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                    <TableHead className="text-right">Unit Price</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                    <TableHead>GL Account</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {lineItems.map((li) => {
                    const suggEntry = glSuggestions?.[li.id];
                    const suggestion = suggEntry?.gl_account ?? li.gl_suggestion ?? null;
                    const suggestionConfidence = suggEntry?.confidence_pct ?? li.gl_suggestion_confidence;
                    const glEdit = glEdits[li.id] ?? {
                      gl_account: li.gl_code ?? "",
                      cost_center: li.cost_center ?? "",
                    };
                    const isConfirmed = confirmedLineIds.has(li.id);
                    return (
                      <TableRow key={li.id}>
                        <TableCell>{li.description}</TableCell>
                        <TableCell className="text-right">{li.quantity}</TableCell>
                        <TableCell className="text-right">${li.unit_price?.toFixed(2)}</TableCell>
                        <TableCell className="text-right">${li.total_price?.toFixed(2)}</TableCell>
                        <TableCell>
                          <div className="space-y-1 min-w-[140px]">
                            <div className="relative">
                              <input
                                className={`border rounded px-2 py-0.5 text-sm w-full focus:outline-none focus:ring-1 focus:ring-blue-500 ${
                                  isConfirmed
                                    ? "border-green-400 bg-green-50 text-gray-900"
                                    : "border-gray-200"
                                }`}
                                placeholder="GL Account"
                                value={glEdit.gl_account}
                                onChange={(e) => {
                                  setConfirmedLineIds((prev) => { const next = new Set(prev); next.delete(li.id); return next; });
                                  setGlEdits((prev) => ({
                                    ...prev,
                                    [li.id]: { ...glEdit, gl_account: e.target.value },
                                  }));
                                }}
                              />
                              {isConfirmed && (
                                <span className="absolute right-2 top-1/2 -translate-y-1/2 text-green-500 text-xs">✓</span>
                              )}
                            </div>
                            {!isConfirmed && suggestion && (
                              <div className="flex items-center gap-1 flex-wrap">
                                <span className="text-xs text-gray-400 italic">{suggestion}</span>
                                <GlConfBadge score={suggestionConfidence} />
                                <button
                                  onClick={() =>
                                    setGlEdits((prev) => ({
                                      ...prev,
                                      [li.id]: { ...glEdit, gl_account: suggestion },
                                    }))
                                  }
                                  className="text-xs text-blue-500 hover:text-blue-700 underline"
                                >
                                  Use
                                </button>
                              </div>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>
                          <button
                            onClick={() => handleConfirmGl(li.id)}
                            disabled={savingGl !== null || !glEdit.gl_account}
                            className={`text-xs px-2 py-1 rounded disabled:opacity-40 whitespace-nowrap ${
                              isConfirmed
                                ? "bg-green-100 text-green-700 hover:bg-green-200"
                                : "bg-gray-100 hover:bg-gray-200"
                            }`}
                          >
                            {savingGl === li.id ? (
                              <span className="w-3 h-3 border-2 border-gray-400 border-t-transparent rounded-full animate-spin inline-block" />
                            ) : isConfirmed ? (
                              "✓ Confirmed"
                            ) : (
                              "Confirm GL"
                            )}
                          </button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                  {lineItems.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={6} className="text-center text-gray-400 py-6">
                        No line items found.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Match */}
        <TabsContent value="match">
          <Card>
            <CardContent className="pt-4">
              {!match ? (
                <p className="text-gray-400 text-sm">No match data available.</p>
              ) : (
                <div className="space-y-5">
                  {/* Header row: match type badge + re-run button */}
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    <div className="flex items-center gap-3">
                      {(() => {
                        const { label, cls } = matchTypeBadge(match.match_type);
                        return (
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
                            {label}
                          </span>
                        );
                      })()}
                      <span
                        className={
                          match.match_status === "matched"
                            ? "text-xs font-medium text-green-700 bg-green-100 px-2 py-0.5 rounded"
                            : match.match_status === "partial"
                            ? "text-xs font-medium text-yellow-700 bg-yellow-100 px-2 py-0.5 rounded"
                            : "text-xs font-medium text-red-700 bg-red-100 px-2 py-0.5 rounded"
                        }
                      >
                        {match.match_status.toUpperCase()}
                      </span>
                    </div>
                    <button
                      onClick={handleRerun3WayMatch}
                      disabled={loadingAction !== null}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50 transition-colors"
                    >
                      {loadingAction === "match3way" ? (
                        <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      ) : (
                        <span>⚡</span>
                      )}
                      Re-run 3-Way Match
                    </button>
                  </div>

                  {/* Summary fields */}
                  <dl className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
                    {[
                      ["PO Number", match.po_number || "—"],
                      ["GR Number", match.gr_number || (match.match_type === "3way" ? "—" : null)],
                      [
                        "Matched At",
                        match.matched_at ? format(new Date(match.matched_at), "MMM d, yyyy HH:mm") : "—",
                      ],
                      [
                        "Amount Variance",
                        match.amount_variance_pct != null
                          ? `${(match.amount_variance_pct * 100).toFixed(2)}%`
                          : "—",
                      ],
                    ]
                      .filter(([, v]) => v !== null)
                      .map(([label, value]) => (
                        <div key={label as string}>
                          <dt className="text-gray-500">{label}</dt>
                          <dd className="font-medium mt-0.5">{value}</dd>
                        </div>
                      ))}
                  </dl>

                  {/* GRN Summary (3-way only) */}
                  {match.match_type === "3way" && match.grn_data && (
                    <div className="rounded-lg border border-purple-200 bg-purple-50/40 p-4">
                      <div className="flex items-center gap-3 mb-3">
                        <span className="text-sm font-semibold text-purple-800">GRN Summary</span>
                        <span className="text-xs text-purple-600 font-mono">{match.grn_data.gr_number}</span>
                        <span className="text-xs text-gray-500">
                          Received {format(new Date(match.grn_data.received_at), "MMM d, yyyy")}
                        </span>
                      </div>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="text-xs">Line#</TableHead>
                            <TableHead className="text-xs">Description</TableHead>
                            <TableHead className="text-right text-xs">Qty Received</TableHead>
                            <TableHead className="text-xs">Unit</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {match.grn_data.lines.map((line) => (
                            <TableRow key={line.id}>
                              <TableCell className="text-xs text-gray-500">{line.line_number}</TableCell>
                              <TableCell className="text-sm">{line.description}</TableCell>
                              <TableCell className="text-right text-sm font-medium">{line.qty_received}</TableCell>
                              <TableCell className="text-xs text-gray-500">{line.unit || "—"}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}

                  {/* Line Matches */}
                  {match.line_matches && match.line_matches.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Line Match Detail</p>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Description</TableHead>
                            <TableHead className="text-right">Invoice Amt</TableHead>
                            <TableHead className="text-right">PO Amt</TableHead>
                            {match.match_type === "3way" && (
                              <>
                                <TableHead className="text-right">Qty Inv</TableHead>
                                <TableHead className="text-right">Qty PO</TableHead>
                                <TableHead className="text-right">Qty Recv</TableHead>
                              </>
                            )}
                            <TableHead className="text-right">Price Var %</TableHead>
                            <TableHead>Status</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {match.line_matches.map((line) => (
                            <React.Fragment key={line.id}>
                            <TableRow className={matchLineClass(line.status)}>
                              <TableCell>{line.description || "—"}</TableCell>
                              <TableCell className="text-right">
                                {line.invoice_amount != null ? `$${line.invoice_amount.toFixed(2)}` : "—"}
                              </TableCell>
                              <TableCell className="text-right">
                                {line.po_amount != null ? `$${line.po_amount.toFixed(2)}` : "—"}
                              </TableCell>
                              {match.match_type === "3way" && (
                                <>
                                  <TableCell className="text-right">
                                    {line.qty_invoiced != null ? line.qty_invoiced : "—"}
                                  </TableCell>
                                  <TableCell className="text-right">
                                    {line.qty_on_po != null ? line.qty_on_po : "—"}
                                  </TableCell>
                                  <TableCell className="text-right">
                                    {line.qty_received != null ? line.qty_received : "—"}
                                  </TableCell>
                                </>
                              )}
                              <TableCell className="text-right">
                                {line.price_variance_pct != null
                                  ? `${(line.price_variance_pct * 100).toFixed(2)}%`
                                  : "—"}
                              </TableCell>
                              <TableCell>
                                <span className={matchStatusClass(line.status)}>
                                  {matchStatusLabel(line.status)}
                                </span>
                              </TableCell>
                            </TableRow>
                            {line.exception_code === "GRN_NOT_FOUND" && (
                              <TableRow className="bg-amber-50">
                                <TableCell
                                  colSpan={match.match_type === "3way" ? 8 : 5}
                                  className="py-2 px-4"
                                >
                                  <span className="text-xs text-amber-700 font-medium">
                                    ⚠️ No Goods Receipt found for this PO line — invoice quantity cannot be verified against receipt.
                                  </span>
                                </TableCell>
                              </TableRow>
                            )}
                            </React.Fragment>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                  {(!match.line_matches || match.line_matches.length === 0) && (
                    <p className="text-sm text-gray-400">No line-level match data available.</p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Exceptions */}
        <TabsContent value="exceptions">
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Code</TableHead>
                    <TableHead>Severity</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead>Raised At</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {exceptions.map((ex) => (
                    <TableRow key={ex.id}>
                      <TableCell className="font-mono text-xs">{ex.code}</TableCell>
                      <TableCell>
                        <Badge variant={ex.severity === "HIGH" ? "destructive" : "secondary"}>
                          {ex.severity}
                        </Badge>
                      </TableCell>
                      <TableCell>{ex.status}</TableCell>
                      <TableCell>{ex.description}</TableCell>
                      <TableCell className="text-sm text-gray-500">
                        {format(new Date(ex.created_at), "MMM d, yyyy")}
                      </TableCell>
                    </TableRow>
                  ))}
                  {exceptions.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-gray-400 py-6">
                        No exceptions.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Approvals */}
        <TabsContent value="approvals">
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Assignee</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Assigned At</TableHead>
                    <TableHead>Decided At</TableHead>
                    <TableHead>Notes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {approvals.map((task) => (
                    <TableRow key={task.id}>
                      <TableCell>{task.assignee_name}</TableCell>
                      <TableCell>
                        <Badge>{task.status}</Badge>
                      </TableCell>
                      <TableCell className="text-sm text-gray-500">
                        {format(new Date(task.assigned_at), "MMM d, yyyy")}
                      </TableCell>
                      <TableCell className="text-sm text-gray-500">
                        {task.decided_at ? format(new Date(task.decided_at), "MMM d, yyyy") : "—"}
                      </TableCell>
                      <TableCell>{task.notes || "—"}</TableCell>
                    </TableRow>
                  ))}
                  {approvals.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-gray-400 py-6">
                        No approval tasks.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Audit Log */}
        <TabsContent value="audit">
          <Card>
            <CardContent className="pt-4">
              <ol className="relative border-l border-gray-200 space-y-4 ml-3">
                {auditLog.map((entry) => (
                  <li key={entry.id} className="ml-4">
                    <div className="absolute w-2.5 h-2.5 bg-gray-400 rounded-full mt-1 -left-1.5 border border-white" />
                    <p className="text-sm font-medium text-gray-900">{entry.action}</p>
                    <p className="text-xs text-gray-500">
                      {entry.actor} · {format(new Date(entry.created_at), "MMM d, yyyy HH:mm")}
                    </p>
                    {entry.detail && (
                      <p className="text-xs text-gray-400 mt-0.5">{entry.detail}</p>
                    )}
                  </li>
                ))}
                {auditLog.length === 0 && (
                  <li className="ml-4 text-sm text-gray-400">No audit entries.</li>
                )}
              </ol>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Toast */}
      {toast && (
        <div
          className={`fixed bottom-4 right-4 z-50 px-4 py-2.5 rounded-lg shadow-lg text-sm font-medium text-white transition-opacity ${
            toast.type === "success" ? "bg-green-600" : "bg-red-600"
          }`}
        >
          {toast.message}
        </div>
      )}
    </div>
  );
}
