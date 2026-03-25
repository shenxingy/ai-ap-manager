// ─── Line Items Tab Component ───

import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { GlConfBadge } from "../components";
import type { LineItem } from "../types";

// ─── Types ───

interface LineItemsTabProps {
  lineItems: LineItem[];
  glSuggestions: Record<string, { gl_account: string; confidence_pct: number }> | undefined;
  glEdits: Record<string, { gl_account: string; cost_center: string }>;
  savingGl: string | null;
  confirmedLineIds: Set<string>;
  setGlEdits: React.Dispatch<React.SetStateAction<Record<string, { gl_account: string; cost_center: string }>>>;
  setConfirmedLineIds: React.Dispatch<React.SetStateAction<Set<string>>>;
  handleConfirmGl: (lineId: string) => void;
  handleConfirmAllGl: () => void;
}

// ─── Component ───

export function LineItemsTab({
  lineItems,
  glSuggestions,
  glEdits,
  savingGl,
  confirmedLineIds,
  setGlEdits,
  setConfirmedLineIds,
  handleConfirmGl,
  handleConfirmAllGl,
}: LineItemsTabProps) {
  return (
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
  );
}
