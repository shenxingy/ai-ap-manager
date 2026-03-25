// ─── Match Tab Component ───

import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { format } from "date-fns";
import {
  matchLineClass,
  matchStatusLabel,
  matchStatusClass,
  matchTypeBadge,
  InspectionBadge,
} from "../components";
import type { MatchResult } from "../types";

// ─── Types ───

interface MatchTabProps {
  match: MatchResult | undefined;
  loadingAction: string | null;
  handleRerun3WayMatch: () => void;
}

// ─── Component ───

export function MatchTab({ match, loadingAction, handleRerun3WayMatch }: MatchTabProps) {
  return (
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

            {/* INSPECTION_FAILED banner */}
            {match.match_status.toUpperCase().includes("INSPECTION_FAILED") && (
              <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
                Cannot approve until inspection report passes
              </div>
            )}

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
                      <TableHead className="text-xs">Inspection</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {match.grn_data.lines.map((line) => (
                      <TableRow key={line.id}>
                        <TableCell className="text-xs text-gray-500">{line.line_number}</TableCell>
                        <TableCell className="text-sm">{line.description}</TableCell>
                        <TableCell className="text-right text-sm font-medium">{line.qty_received}</TableCell>
                        <TableCell className="text-xs text-gray-500">{line.unit || "—"}</TableCell>
                        <TableCell><InspectionBadge status={match.grn_data!.inspection_status} /></TableCell>
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
  );
}
