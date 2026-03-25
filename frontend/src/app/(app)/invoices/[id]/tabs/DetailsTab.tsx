// ─── Details Tab Component ───

import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { format } from "date-fns";
import { ConfidenceDot, fraudBadge } from "../components";
import type { Invoice } from "../types";

// ─── Types ───

interface DetailsTabProps {
  invoice: Invoice;
  editingField: string | null;
  editValue: string;
  savingField: boolean;
  comparisonOpen: boolean;
  setEditingField: (field: string | null) => void;
  setEditValue: (value: string) => void;
  setComparisonOpen: React.Dispatch<React.SetStateAction<boolean>>;
  handleSaveField: (fieldName: string, value: string) => void;
}

// ─── Detail Fields Builder ───

function buildDetailFields(invoice: Invoice) {
  return [
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
}

// ─── Component ───

export function DetailsTab({
  invoice,
  editingField,
  editValue,
  savingField,
  comparisonOpen,
  setEditingField,
  setEditValue,
  setComparisonOpen,
  handleSaveField,
}: DetailsTabProps) {
  const detailFields = buildDetailFields(invoice);

  return (
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
                      {savingField ? "..." : "Save"}
                    </button>
                    <button
                      onClick={() => setEditingField(null)}
                      className="text-xs text-gray-400 hover:text-gray-600"
                    >
                      x
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

        {/* ─── FX Normalized Amount ─── */}
        {invoice.normalized_amount_usd != null && invoice.currency !== "USD" && (
          <p className="text-sm text-muted-foreground mt-3">
            ≈ ${invoice.normalized_amount_usd.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD
            {invoice.fx_rate_used != null && invoice.fx_rate_date != null && (
              <span> (rate: {invoice.fx_rate_used} on {invoice.fx_rate_date})</span>
            )}
          </p>
        )}

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
  );
}
