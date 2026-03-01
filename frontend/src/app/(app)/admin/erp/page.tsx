"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Upload, CheckCircle2, XCircle } from "lucide-react";
import api from "@/lib/api";

// ─── Types ───

interface SyncResult {
  created: number;
  updated: number;
  skipped: number;
  errors: string[];
}

interface TabConfig {
  key: "sap" | "oracle";
  label: string;
  endpoint: string;
  delimiter: string;
  required: string[];
}

// ─── Tab configs ───

const TABS: TabConfig[] = [
  {
    key: "sap",
    label: "SAP POs",
    endpoint: "/admin/erp/sync/sap-pos",
    delimiter: ";",
    required: [
      "PO_NUMBER",
      "VENDOR_CODE",
      "VENDOR_NAME",
      "LINE_NUMBER",
      "DESCRIPTION",
      "QUANTITY",
      "UNIT_PRICE",
      "CURRENCY",
    ],
  },
  {
    key: "oracle",
    label: "Oracle GRNs",
    endpoint: "/admin/erp/sync/oracle-grns",
    delimiter: ",",
    required: [
      "RECEIPT_NUMBER",
      "PO_NUMBER",
      "LINE_NUMBER",
      "ITEM_DESCRIPTION",
      "QUANTITY_RECEIVED",
      "RECEIVED_DATE",
    ],
  },
];

// ─── ERPTab component ───

function ERPTab({ config }: { config: TabConfig }) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SyncResult | null>(null);
  const [detectedColumns, setDetectedColumns] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (f: File) => {
    setFile(f);
    setResult(null);
    // Peek first line to detect columns
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = (e.target?.result as string) ?? "";
      const firstLine = text.split(/\r?\n/)[0] ?? "";
      const cols = firstLine.split(config.delimiter).map((c) => c.trim());
      setDetectedColumns(cols);
    };
    reader.readAsText(f);
  };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await api.post<SyncResult>(config.endpoint, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(res.data);
    } catch {
      // api interceptor handles error display
    } finally {
      setLoading(false);
    }
  };

  const columnStatus = config.required.map((col) => ({
    col,
    found: detectedColumns.some(
      (d) => d.toUpperCase() === col.toUpperCase()
    ),
  }));

  const allColumnsPresent = columnStatus.every((c) => c.found);

  return (
    <div className="space-y-5">
      {/* File input */}
      <div
        onClick={() => inputRef.current?.click()}
        className="flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 cursor-pointer py-10 hover:border-gray-400 transition-colors"
      >
        <Upload className="h-7 w-7 text-gray-400" />
        <p className="text-sm text-gray-600">
          {file ? (
            <span className="font-medium text-gray-900">{file.name}</span>
          ) : (
            <>
              Click to select a CSV file{" "}
              <span className="text-gray-400">
                (delimiter: &ldquo;{config.delimiter}&rdquo;)
              </span>
            </>
          )}
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFileChange(f);
          }}
        />
      </div>

      {/* Column validation chips */}
      {file && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Required Columns
          </p>
          <div className="flex flex-wrap gap-2">
            {columnStatus.map(({ col, found }) => (
              <span
                key={col}
                className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full font-mono ${
                  found
                    ? "bg-green-100 text-green-800"
                    : "bg-red-100 text-red-800"
                }`}
              >
                {found ? (
                  <CheckCircle2 className="h-3 w-3" />
                ) : (
                  <XCircle className="h-3 w-3" />
                )}
                {col}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Upload button */}
      {file && (
        <div className="flex items-center gap-3">
          <Button
            onClick={handleUpload}
            disabled={loading || !allColumnsPresent}
          >
            {loading ? "Uploading…" : "Upload & Sync"}
          </Button>
          {!allColumnsPresent && (
            <p className="text-xs text-red-600">
              Missing required columns — check your CSV headers
            </p>
          )}
        </div>
      )}

      {/* Result summary */}
      {result && (
        <Card className="border-gray-200">
          <CardContent className="pt-4 space-y-3">
            <div className="flex flex-wrap gap-5 text-sm">
              <span className="text-green-700 font-medium">
                Created: {result.created}
              </span>
              <span className="text-blue-700 font-medium">
                Updated: {result.updated}
              </span>
              <span className="text-gray-500">Skipped: {result.skipped}</span>
              {result.errors.length > 0 && (
                <span className="text-red-700 font-medium">
                  Errors: {result.errors.length}
                </span>
              )}
            </div>

            {result.errors.length > 0 && (
              <div className="rounded-md bg-red-50 border border-red-200 p-3 space-y-1 max-h-48 overflow-y-auto">
                {result.errors.map((err, i) => (
                  <p key={i} className="text-xs text-red-800">
                    {err}
                  </p>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ─── Page ───

export default function ERPSyncPage() {
  const router = useRouter();
  const { user } = useAuthStore();

  useEffect(() => {
    if (user && user.role !== "ADMIN") {
      router.push("/unauthorized");
    }
  }, [user, router]);

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">ERP CSV Sync</h1>
        <p className="text-sm text-gray-500 mt-1">
          Upload SAP PO exports or Oracle GRN exports to sync purchase orders
          and goods receipts. Existing records are upserted by their unique
          identifiers.
        </p>
      </div>

      <Tabs defaultValue="sap">
        <TabsList>
          {TABS.map((t) => (
            <TabsTrigger key={t.key} value={t.key}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>

        {TABS.map((t) => (
          <TabsContent key={t.key} value={t.key} className="mt-4">
            <ERPTab config={t} />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
