// ─── Invoice Action Handlers Hook ───

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";

// ─── Toast Type ───

export interface Toast {
  message: string;
  type: "success" | "error";
}

// ─── Hook ───

export function useInvoiceActions(id: string) {
  const queryClient = useQueryClient();

  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);

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

  // Communications compose state
  const [msgBody, setMsgBody] = useState("");
  const [msgMode, setMsgMode] = useState<"internal" | "vendor">("vendor");

  function showToast(message: string, type: "success" | "error") {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3500);
  }

  // ─── Action Bar Handlers ───

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

  async function handleDownload(invoiceNumber: string | undefined) {
    setLoadingAction("download");
    try {
      const response = await api.get(`/invoices/${id}/download`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `invoice-${invoiceNumber || id}.pdf`;
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

  // ─── Field Editing ───

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

  // ─── GL Editing ───

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

  function invalidateInvoice() {
    return queryClient.invalidateQueries({ queryKey: ["invoice", id] });
  }

  return {
    // Toast
    toast,
    // Action bar
    loadingAction,
    handleRerunExtraction,
    handleRetriggerMatch,
    handleRerun3WayMatch,
    handleDownload,
    // Field editing
    editingField, setEditingField,
    editValue, setEditValue,
    savingField,
    handleSaveField,
    // Extraction comparison
    comparisonOpen, setComparisonOpen,
    // GL editing
    glEdits, setGlEdits,
    savingGl,
    confirmedLineIds, setConfirmedLineIds,
    handleConfirmGl,
    handleConfirmAllGl,
    // Communications
    msgBody, setMsgBody,
    msgMode, setMsgMode,
    // Utility
    invalidateInvoice,
  };
}
