"use client";

import { useState, useRef, useCallback } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { CheckCircle2, XCircle, Upload, Download, AlertTriangle } from "lucide-react";
import api from "@/lib/api";

// ─── Types ───

interface ImportRowError {
  row: number;
  field: string;
  message: string;
}

interface ImportResult {
  created: number;
  updated: number;
  skipped: number;
  errors: ImportRowError[];
  warnings?: string[];
}

interface TabConfig {
  key: "pos" | "grns" | "vendors";
  label: string;
  endpoint: string;
  required: string[];
}

// ─── Constants ───

const TABS: TabConfig[] = [
  {
    key: "pos",
    label: "Purchase Orders",
    endpoint: "/import/pos",
    required: ["po_number", "vendor_name", "total_amount", "currency", "issue_date"],
  },
  {
    key: "grns",
    label: "Goods Receipts",
    endpoint: "/import/grns",
    required: ["gr_number", "po_number", "received_date", "total_received_value"],
  },
  {
    key: "vendors",
    label: "Vendors",
    endpoint: "/import/vendors",
    required: ["vendor_name", "tax_id", "payment_terms", "currency"],
  },
];

// ─── CSV parsing helpers ───

function parseCSVPreview(text: string): { headers: string[]; rows: string[][] } {
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  if (!lines.length) return { headers: [], rows: [] };
  const parse = (line: string) =>
    line.split(",").map((c) => c.trim().replace(/^"|"$/g, ""));
  const headers = parse(lines[0]);
  const rows = lines.slice(1, 11).map(parse);
  return { headers, rows };
}

function mapHeaders(csvHeaders: string[], required: string[]): Record<string, boolean> {
  const lowered = csvHeaders.map((h) => h.toLowerCase().trim());
  return Object.fromEntries(
    required.map((req) => [req, lowered.includes(req.toLowerCase())])
  );
}

function generateErrorCSV(errors: ImportRowError[]): string {
  const header = "row,field,message";
  const rows = errors.map(
    (e) => `${e.row},"${e.field}","${e.message.replace(/"/g, '""')}"`
  );
  return [header, ...rows].join("\n");
}

function downloadBlob(content: string, filename: string) {
  const blob = new Blob([content], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ─── ImportTab component ───

function ImportTab({ config }: { config: TabConfig }) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<{ headers: string[]; rows: string[][] } | null>(null);
  const [columnMap, setColumnMap] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    (f: File) => {
      setFile(f);
      setResult(null);
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target?.result as string;
        const parsed = parseCSVPreview(text);
        setPreview(parsed);
        setColumnMap(mapHeaders(parsed.headers, config.required));
      };
      reader.readAsText(f);
    },
    [config.required]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const f = e.dataTransfer.files[0];
      if (f && f.name.endsWith(".csv")) handleFile(f);
    },
    [handleFile]
  );

  const handleImport = async () => {
    if (!file) return;
    setLoading(true);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await api.post<ImportResult>(config.endpoint, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(res.data);
    } catch {
      // api interceptor handles error toast
    } finally {
      setLoading(false);
    }
  };

  const allRequired = Object.values(columnMap).every(Boolean);

  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed cursor-pointer py-10 transition-colors
          ${dragOver ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-gray-400 bg-gray-50"}`}
      >
        <Upload className="h-8 w-8 text-gray-400" />
        <p className="text-sm text-gray-600">
          {file ? (
            <span className="font-medium text-gray-900">{file.name}</span>
          ) : (
            <>Drag & drop a CSV file here, or <span className="text-blue-600 underline">browse</span></>
          )}
        </p>
        <p className="text-xs text-gray-400">Required columns: {config.required.join(", ")}</p>
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
        />
      </div>

      {/* Column mapping status */}
      {file && preview && (
        <div className="flex flex-wrap gap-2">
          {config.required.map((col) => {
            const found = columnMap[col] ?? false;
            return (
              <span
                key={col}
                className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full font-mono
                  ${found ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}`}
              >
                {found ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                {col}
              </span>
            );
          })}
        </div>
      )}

      {/* Preview table */}
      {preview && preview.headers.length > 0 && (
        <Card>
          <CardHeader className="py-3">
            <CardTitle className="text-sm font-medium text-gray-700">
              Preview (first {preview.rows.length} rows)
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  {preview.headers.map((h) => (
                    <TableHead key={h} className="text-xs whitespace-nowrap">{h}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {preview.rows.map((row, i) => (
                  <TableRow key={i}>
                    {row.map((cell, j) => (
                      <TableCell key={j} className="text-xs whitespace-nowrap max-w-[160px] truncate">{cell}</TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Import button */}
      {file && (
        <div className="flex items-center gap-3">
          <Button
            onClick={handleImport}
            disabled={loading || !allRequired}
            className="min-w-[120px]"
          >
            {loading ? "Importing…" : "Import"}
          </Button>
          {!allRequired && (
            <p className="text-xs text-red-600">Missing required columns — check your CSV</p>
          )}
        </div>
      )}

      {/* Result card */}
      {result && (
        <Card className="border-gray-200">
          <CardContent className="pt-4 space-y-3">
            <div className="flex flex-wrap gap-4 text-sm">
              <span className="text-green-700 font-medium">{result.created} created</span>
              <span className="text-blue-700 font-medium">{result.updated} updated</span>
              <span className="text-gray-500">{result.skipped} skipped</span>
              {result.errors.length > 0 && (
                <span className="text-red-700 font-medium">{result.errors.length} errors</span>
              )}
            </div>

            {/* Warnings */}
            {result.warnings && result.warnings.length > 0 && (
              <div className="rounded-md bg-yellow-50 border border-yellow-200 p-3 space-y-1">
                {result.warnings.map((w, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs text-yellow-800">
                    <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                    {w}
                  </div>
                ))}
              </div>
            )}

            {/* Errors list */}
            {result.errors.length > 0 && (
              <div className="space-y-2">
                <div className="rounded-md border overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs w-16">Row</TableHead>
                        <TableHead className="text-xs w-32">Field</TableHead>
                        <TableHead className="text-xs">Message</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {result.errors.slice(0, 20).map((e, i) => (
                        <TableRow key={i}>
                          <TableCell className="text-xs">{e.row}</TableCell>
                          <TableCell className="text-xs font-mono">{e.field}</TableCell>
                          <TableCell className="text-xs text-red-700">{e.message}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                {result.errors.length > 20 && (
                  <p className="text-xs text-gray-500">…and {result.errors.length - 20} more errors</p>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    downloadBlob(
                      generateErrorCSV(result.errors),
                      `import-errors-${config.key}-${Date.now()}.csv`
                    )
                  }
                >
                  <Download className="h-3.5 w-3.5 mr-1.5" />
                  Download Error Report
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ─── Page ───

export default function ImportPage() {
  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">CSV Bulk Import</h1>
        <p className="text-sm text-gray-500 mt-1">
          Import Purchase Orders, Goods Receipts, and Vendors from CSV files.
          Existing records are updated by their unique identifiers.
        </p>
      </div>

      <Tabs defaultValue="pos">
        <TabsList>
          {TABS.map((t) => (
            <TabsTrigger key={t.key} value={t.key}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>

        {TABS.map((t) => (
          <TabsContent key={t.key} value={t.key} className="mt-4">
            <ImportTab config={t} />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
