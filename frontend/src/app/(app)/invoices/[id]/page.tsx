"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
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
  invoice_date: string | null;
  due_date: string | null;
  currency: string;
  created_at: string;
}

interface LineItem {
  id: string;
  description: string;
  quantity: number;
  unit_price: number;
  total_price: number;
  gl_code: string | null;
  gl_suggestion: string | null;
}

interface MatchResult {
  match_status: string;
  po_number: string | null;
  gr_number: string | null;
  variance_pct: number | null;
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

// ─── Fraud Badge ───

function fraudBadge(score: number | null): string {
  if (score === null) return "N/A";
  if (score >= 0.9) return "🔴🔴 CRITICAL";
  if (score >= 0.7) return "🔴 HIGH";
  if (score >= 0.4) return "🟡 MEDIUM";
  return "🟢 LOW";
}

// ─── Page ───

export default function InvoiceDetailPage() {
  const { id } = useParams<{ id: string }>();

  const { data: invoice } = useQuery<Invoice>({
    queryKey: ["invoice", id],
    queryFn: () => api.get(`/invoices/${id}`).then((r) => r.data),
  });

  const { data: lineItems = [] } = useQuery<LineItem[]>({
    queryKey: ["invoice-lines", id],
    queryFn: () => api.get(`/invoices/${id}/line-items`).then((r) => r.data),
  });

  const { data: glSuggestions } = useQuery<Record<string, string>>({
    queryKey: ["invoice-gl", id],
    queryFn: () =>
      api.get(`/invoices/${id}/gl-suggestions`).then((r) => {
        const map: Record<string, string> = {};
        (r.data.suggestions ?? []).forEach((s: { line_item_id: string; gl_code: string }) => {
          map[s.line_item_id] = s.gl_code;
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

  if (!invoice) {
    return <div className="py-12 text-center text-gray-500">Loading invoice...</div>;
  }

  return (
    <div className="space-y-5">
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
                {[
                  ["Invoice Number", invoice.invoice_number],
                  ["Vendor", invoice.vendor_name_raw],
                  ["Amount", `${invoice.currency} ${invoice.total_amount?.toLocaleString()}`],
                  ["Status", invoice.status],
                  ["Invoice Date", invoice.invoice_date ? format(new Date(invoice.invoice_date), "MMM d, yyyy") : "—"],
                  ["Due Date", invoice.due_date ? format(new Date(invoice.due_date), "MMM d, yyyy") : "—"],
                  ["Received", format(new Date(invoice.created_at), "MMM d, yyyy HH:mm")],
                  ["Fraud Score", fraudBadge(invoice.fraud_score)],
                ].map(([label, value]) => (
                  <div key={label}>
                    <dt className="text-gray-500">{label}</dt>
                    <dd className="font-medium mt-0.5">{value}</dd>
                  </div>
                ))}
              </dl>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Line Items */}
        <TabsContent value="lines">
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Description</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                    <TableHead className="text-right">Unit Price</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                    <TableHead>GL Code</TableHead>
                    <TableHead>GL Suggestion</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {lineItems.map((li) => (
                    <TableRow key={li.id}>
                      <TableCell>{li.description}</TableCell>
                      <TableCell className="text-right">{li.quantity}</TableCell>
                      <TableCell className="text-right">${li.unit_price?.toFixed(2)}</TableCell>
                      <TableCell className="text-right">${li.total_price?.toFixed(2)}</TableCell>
                      <TableCell>{li.gl_code || "—"}</TableCell>
                      <TableCell className="text-blue-600">
                        {glSuggestions?.[li.id] ?? li.gl_suggestion ?? "—"}
                      </TableCell>
                    </TableRow>
                  ))}
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
                <dl className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
                  {[
                    ["Match Status", match.match_status],
                    ["PO Number", match.po_number || "—"],
                    ["GR Number", match.gr_number || "—"],
                    ["Variance", match.variance_pct != null ? `${(match.variance_pct * 100).toFixed(2)}%` : "—"],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <dt className="text-gray-500">{label}</dt>
                      <dd className="font-medium mt-0.5">{value}</dd>
                    </div>
                  ))}
                </dl>
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
                      <TableCell><Badge variant={ex.severity === "HIGH" ? "destructive" : "secondary"}>{ex.severity}</Badge></TableCell>
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
                      <TableCell><Badge>{task.status}</Badge></TableCell>
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
                    {entry.detail && <p className="text-xs text-gray-400 mt-0.5">{entry.detail}</p>}
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
    </div>
  );
}
