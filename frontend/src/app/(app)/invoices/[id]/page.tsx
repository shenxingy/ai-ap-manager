"use client";

import React from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type {
  Invoice,
  LineItem,
  MatchResult,
  ExceptionItem,
  ApprovalTask,
  AuditEntry,
  VendorMessage,
  ComplianceDoc,
} from "./types";
import { fraudBadge, RecordPaymentDialog } from "./components";
import { useInvoiceActions } from "./useInvoiceActions";
import {
  DetailsTab,
  LineItemsTab,
  MatchTab,
  ExceptionsTab,
  ApprovalsTab,
  AuditTab,
  CommunicationsTab,
} from "./tabs";

// ─── Page ───

export default function InvoiceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const user = useAuthStore((state) => state.user);
  const actions = useInvoiceActions(id);

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

  const { data: messages = [], refetch: refetchMessages } = useQuery<VendorMessage[]>({
    queryKey: ["invoice-messages", id],
    queryFn: () => api.get(`/invoices/${id}/messages`).then((r) => r.data),
    refetchInterval: 10000,
  });

  const { data: vendorCompliance = [] } = useQuery<ComplianceDoc[]>({
    queryKey: ["vendor-compliance", invoice?.vendor_id],
    queryFn: () => api.get(`/vendors/${invoice?.vendor_id}/compliance-docs`).then((r) => r.data),
    enabled: !!invoice?.vendor_id,
  });

  const sendMessageMutation = useMutation({
    mutationFn: (payload: { body: string; is_internal: boolean }) =>
      api.post(`/invoices/${id}/messages`, payload).then((r) => r.data),
    onSuccess: () => {
      actions.setMsgBody("");
      void refetchMessages();
    },
  });

  if (!invoice) {
    return <div className="py-12 text-center text-gray-500">Loading invoice...</div>;
  }

  // ─── Render ───

  return (
    <div className="space-y-5">
      {/* Fraud Banners */}
      {invoice.fraud_score != null && invoice.fraud_score >= 0.9 && (
        <div className="border-l-4 border-l-red-700 bg-red-50 p-4 rounded">
          <p className="text-sm font-semibold text-red-900">⚠️ Dual Authorization Required</p>
          <p className="text-sm text-red-800 mt-1">This invoice&apos;s CRITICAL fraud score ({(invoice.fraud_score * 100).toFixed(0)}%) requires 2 ADMIN approvals before payment.</p>
        </div>
      )}
      {invoice.fraud_score != null && invoice.fraud_score >= 0.6 && invoice.fraud_score < 0.9 && (
        <div className="border-l-4 border-l-amber-500 bg-amber-50 p-4 rounded">
          <p className="text-sm font-semibold text-amber-800">⚠ Fraud Risk Alert</p>
          <p className="text-sm text-amber-700 mt-1">This invoice has a high fraud score ({(invoice.fraud_score * 100).toFixed(0)}%) and requires immediate review before approval.</p>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-wrap items-start gap-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Invoice {invoice.invoice_number || invoice.id.slice(0, 8)}</h2>
          <p className="text-gray-500 mt-0.5">{invoice.vendor_name_raw}</p>
        </div>
        <div className="flex items-center gap-2 ml-auto flex-wrap">
          <span className="text-xl font-semibold text-gray-700">
            {invoice.currency} {invoice.total_amount?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </span>
          <Badge>{invoice.status}</Badge>
          {invoice.payment_status && <Badge variant="outline" className="border-green-400 text-green-700">Paid</Badge>}
          <Badge variant="outline">{fraudBadge(invoice.fraud_score)}</Badge>
          {invoice.is_duplicate && <Badge variant="destructive">Duplicate</Badge>}
        </div>
      </div>

      {/* Info Banners */}
      {vendorCompliance.some((doc) => doc.status === "expired" || doc.status === "missing") && (
        <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-2 rounded text-sm">⚠️ Vendor has expired or missing compliance documents</div>
      )}
      {invoice.is_recurring && (
        <div className="bg-blue-50 border border-blue-200 text-blue-800 px-4 py-2 rounded text-sm">🔄 Recurring invoice detected — 1-click approval may be available</div>
      )}
      {invoice.is_duplicate && (
        <div className="bg-red-50 border border-red-200 text-red-800 px-4 py-2 rounded text-sm">⚠️ Duplicate invoice detected — this invoice matches an existing submission and requires review before approval.</div>
      )}

      {/* Action Bar */}
      <div className="flex gap-2 flex-wrap">
        {([
          { key: "extract", icon: "⟳", label: "Re-run Extraction", onClick: actions.handleRerunExtraction },
          { key: "match", icon: "⚡", label: "Trigger Re-match", onClick: actions.handleRetriggerMatch },
          { key: "download", icon: "↓", label: "Download Original", onClick: () => actions.handleDownload(invoice.invoice_number) },
        ] as const).map((btn) => (
          <button
            key={btn.key}
            onClick={btn.onClick}
            disabled={actions.loadingAction !== null}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            {actions.loadingAction === btn.key
              ? <span className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
              : <span>{btn.icon}</span>}
            {btn.label}
          </button>
        ))}
        {invoice.status === "approved" && user?.role === "ADMIN" && (
          <RecordPaymentDialog invoiceId={invoice.id} onSuccess={() => actions.invalidateInvoice()} />
        )}
      </div>

      {/* ─── Tabs ─── */}
      <Tabs defaultValue="details">
        <TabsList>
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="lines">Line Items</TabsTrigger>
          <TabsTrigger value="match">Match</TabsTrigger>
          <TabsTrigger value="exceptions">Exceptions</TabsTrigger>
          <TabsTrigger value="approvals">Approvals</TabsTrigger>
          <TabsTrigger value="audit">Audit Log</TabsTrigger>
          <TabsTrigger value="communications">
            Communications
            {messages.filter((m) => m.direction === "inbound").length > 0 && (
              <span className="ml-1.5 inline-flex items-center justify-center w-4 h-4 rounded-full bg-orange-500 text-white text-[10px] font-bold">
                {messages.filter((m) => m.direction === "inbound").length}
              </span>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="details">
          <DetailsTab
            invoice={invoice}
            editingField={actions.editingField}
            editValue={actions.editValue}
            savingField={actions.savingField}
            comparisonOpen={actions.comparisonOpen}
            setEditingField={actions.setEditingField}
            setEditValue={actions.setEditValue}
            setComparisonOpen={actions.setComparisonOpen}
            handleSaveField={actions.handleSaveField}
          />
        </TabsContent>

        <TabsContent value="lines">
          <LineItemsTab
            lineItems={lineItems}
            glSuggestions={glSuggestions}
            glEdits={actions.glEdits}
            savingGl={actions.savingGl}
            confirmedLineIds={actions.confirmedLineIds}
            setGlEdits={actions.setGlEdits}
            setConfirmedLineIds={actions.setConfirmedLineIds}
            handleConfirmGl={actions.handleConfirmGl}
            handleConfirmAllGl={actions.handleConfirmAllGl}
          />
        </TabsContent>

        <TabsContent value="match">
          <MatchTab
            match={match}
            loadingAction={actions.loadingAction}
            handleRerun3WayMatch={actions.handleRerun3WayMatch}
          />
        </TabsContent>

        <TabsContent value="exceptions">
          <ExceptionsTab exceptions={exceptions} />
        </TabsContent>

        <TabsContent value="approvals">
          <ApprovalsTab approvals={approvals} />
        </TabsContent>

        <TabsContent value="audit">
          <AuditTab auditLog={auditLog} />
        </TabsContent>

        <TabsContent value="communications">
          <CommunicationsTab
            messages={messages}
            msgBody={actions.msgBody}
            msgMode={actions.msgMode}
            isSending={sendMessageMutation.isPending}
            setMsgBody={actions.setMsgBody}
            setMsgMode={actions.setMsgMode}
            onSend={() =>
              sendMessageMutation.mutate({
                body: actions.msgBody,
                is_internal: actions.msgMode === "internal",
              })
            }
          />
        </TabsContent>
      </Tabs>

      {/* Toast */}
      {actions.toast && (
        <div
          className={`fixed bottom-4 right-4 z-50 px-4 py-2.5 rounded-lg shadow-lg text-sm font-medium text-white transition-opacity ${
            actions.toast.type === "success" ? "bg-green-600" : "bg-red-600"
          }`}
        >
          {actions.toast.message}
        </div>
      )}
    </div>
  );
}
