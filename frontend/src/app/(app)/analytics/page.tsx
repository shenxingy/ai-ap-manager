"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { InboxIcon } from "lucide-react";
import { format } from "date-fns";
import { useAuthStore } from "@/store/auth";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import api from "@/lib/api";

// ─── Types ───

interface ProcessMiningStep {
  step: string;
  from_status: string;
  to_status: string;
  median_hours: number;
  p90_hours: number;
  invoice_count: number;
}

interface Anomaly {
  vendor_id: string;
  vendor_name: string;
  period: string;
  exception_rate: number;
  z_score: number;
  direction: string;
}

interface RootCauseReport {
  id: string;
  status: "pending" | "complete" | "failed";
  narrative: string | null;
  created_at: string;
}

interface GenerateReportResponse {
  report_id: string;
}

interface ReportsListResponse {
  items: RootCauseReport[];
}

// ─── Helpers ───

function stepColor(median_hours: number): string {
  if (median_hours < 24) return "#22c55e"; // green
  if (median_hours < 72) return "#eab308"; // yellow
  return "#ef4444"; // red
}

function SkeletonBar() {
  return (
    <div className="space-y-2">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="animate-pulse bg-gray-200 rounded h-8 w-full" />
      ))}
    </div>
  );
}

function extractApiError(err: unknown): string {
  return (
    (err as { response?: { data?: { detail?: string } } })?.response?.data
      ?.detail ?? "Failed to generate report"
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

// ─── Process Mining Section ───

function ProcessMiningSection() {
  const { data = [], isLoading } = useQuery<ProcessMiningStep[]>({
    queryKey: ["analytics-process-mining"],
    queryFn: () => api.get("/analytics/process-mining").then((r) => r.data),
    refetchInterval: 5 * 60 * 1000,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          Process Mining — Step Durations
        </CardTitle>
        <p className="text-xs text-gray-500 mt-0.5">
          Median and P90 hours per invoice processing step
        </p>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <SkeletonBar />
        ) : data.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-400">
            <InboxIcon className="h-10 w-10 mb-2" />
            <p className="text-sm">
              No process data yet — process some invoices to see step durations
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <ResponsiveContainer width="100%" height={data.length * 52 + 40}>
              <BarChart
                data={data}
                layout="vertical"
                margin={{ top: 5, right: 40, left: 160, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis
                  type="number"
                  unit="h"
                  tick={{ fontSize: 11 }}
                  label={{
                    value: "Hours",
                    position: "insideRight",
                    offset: 10,
                    fontSize: 11,
                  }}
                />
                <YAxis
                  type="category"
                  dataKey="step"
                  width={155}
                  tick={{ fontSize: 11 }}
                />
                <Tooltip
                  formatter={(
                    value: number | undefined,
                    name: string | undefined
                  ) => [
                    value != null ? `${value}h` : "—",
                    name === "median_hours" ? "Median" : "P90",
                  ]}
                />
                <Bar dataKey="median_hours" name="Median" radius={[0, 4, 4, 0]}>
                  {data.map((entry) => (
                    <Cell key={entry.step} fill={stepColor(entry.median_hours)} />
                  ))}
                </Bar>
                {/* P90 reference lines per step rendered as separate bars with low opacity */}
                <Bar
                  dataKey="p90_hours"
                  name="P90"
                  fill="#94a3b8"
                  opacity={0.4}
                  radius={[0, 4, 4, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
            <div className="flex items-center gap-4 text-xs text-gray-500">
              <span className="flex items-center gap-1">
                <span className="inline-block w-3 h-3 rounded-sm bg-green-500" />{" "}
                &lt; 24h (fast)
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-3 h-3 rounded-sm bg-yellow-400" />{" "}
                24–72h (normal)
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-3 h-3 rounded-sm bg-red-500" />{" "}
                ≥ 72h (slow)
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-3 h-3 rounded-sm bg-slate-400 opacity-50" />{" "}
                P90
              </span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Anomalies Section ───

function AnomalyCard({ anomaly }: { anomaly: Anomaly }) {
  const isSpike = anomaly.direction === "spike";
  return (
    <div className="flex items-start justify-between p-4 rounded-lg border border-gray-200 bg-white">
      <div>
        <p className="text-sm font-semibold text-gray-900">
          {anomaly.vendor_name}
        </p>
        <p className="text-xs text-gray-500 mt-0.5">
          Period starting {anomaly.period}
        </p>
        <p className="text-xs text-gray-600 mt-1">
          Exception rate:{" "}
          <span className="font-medium">
            {(anomaly.exception_rate * 100).toFixed(1)}%
          </span>
        </p>
      </div>
      <div className="text-right space-y-1">
        <span
          className={`inline-block px-2 py-0.5 rounded text-xs font-bold ${
            isSpike
              ? "bg-red-100 text-red-700"
              : "bg-blue-100 text-blue-700"
          }`}
        >
          {isSpike ? "▲" : "▼"} z={anomaly.z_score > 0 ? "+" : ""}
          {anomaly.z_score.toFixed(2)}
        </span>
        <p className="text-xs text-gray-400 capitalize">{anomaly.direction}</p>
      </div>
    </div>
  );
}

function AnomaliesSection() {
  const { data = [], isLoading } = useQuery<Anomaly[]>({
    queryKey: ["analytics-anomalies"],
    queryFn: () => api.get("/analytics/anomalies").then((r) => r.data),
    refetchInterval: 10 * 60 * 1000,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Vendor Anomalies</CardTitle>
        <p className="text-xs text-gray-500 mt-0.5">
          Vendor-windows with exception rate &gt; 2 std deviations from baseline
          (last 6 months)
        </p>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="animate-pulse bg-gray-200 rounded h-16 w-full"
              />
            ))}
          </div>
        ) : data.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-400">
            <InboxIcon className="h-10 w-10 mb-2" />
            <p className="text-sm">
              No anomalies detected in the last 6 months
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {data.map((a) => (
              <AnomalyCard key={`${a.vendor_id}-${a.period}`} anomaly={a} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Root Cause Report Section ───

function RootCauseReportSection({
  onError,
}: {
  onError: (msg: string) => void;
}) {
  const { user } = useAuthStore();
  const queryClient = useQueryClient();
  const [activeReportId, setActiveReportId] = useState<string | null>(null);
  const [activeReport, setActiveReport] = useState<RootCauseReport | null>(
    null
  );
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const canGenerate =
    user?.role === "ADMIN" || user?.role === "AP_ANALYST";

  const { data: reportsData, isLoading: reportsLoading } =
    useQuery<ReportsListResponse>({
      queryKey: ["analytics-reports"],
      queryFn: () => api.get("/analytics/reports").then((r) => r.data),
    });

  const pastReports = (reportsData?.items ?? []).slice(0, 5);

  const generateMutation = useMutation({
    mutationFn: () =>
      api
        .post("/analytics/root-cause-report")
        .then((r) => r.data as GenerateReportResponse),
    onSuccess: (data) => {
      setActiveReportId(data.report_id);
      setActiveReport({ id: data.report_id, status: "pending", narrative: null, created_at: new Date().toISOString() });
    },
    onError: (err) => onError(extractApiError(err)),
  });

  // Start polling when activeReportId is set
  useEffect(() => {
    if (!activeReportId) return;

    const interval = setInterval(async () => {
      try {
        const res = await api.get(`/analytics/reports/${activeReportId}`);
        const report = res.data as RootCauseReport;
        setActiveReport(report);

        if (report.status !== "pending") {
          clearInterval(interval);
          pollRef.current = null;
          queryClient.invalidateQueries({ queryKey: ["analytics-reports"] });
        }
      } catch {
        clearInterval(interval);
        pollRef.current = null;
        onError("Failed to fetch report status");
      }
    }, 3000);

    pollRef.current = interval;
    return () => clearInterval(interval);
  }, [activeReportId, queryClient, onError]);

  function toggleExpand(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base">Root Cause Report</CardTitle>
            <p className="text-xs text-gray-500 mt-0.5">
              AI-generated narrative analysis of AP exceptions and bottlenecks
            </p>
          </div>
          {canGenerate && (
            <Button
              onClick={() => generateMutation.mutate()}
              disabled={
                generateMutation.isPending ||
                activeReport?.status === "pending"
              }
              size="sm"
            >
              {generateMutation.isPending || activeReport?.status === "pending"
                ? "Generating…"
                : "Generate Root Cause Report"}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Active report result */}
        {activeReport && (
          <div className="rounded-lg border p-4">
            {activeReport.status === "pending" ? (
              <div className="flex items-center gap-3 text-sm text-gray-500">
                <svg
                  className="animate-spin h-4 w-4 text-blue-500 shrink-0"
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
                Analyzing AP exceptions — this may take a moment…
              </div>
            ) : activeReport.status === "failed" ? (
              <p className="text-sm text-red-600">
                Report generation failed. Please try again.
              </p>
            ) : (
              <div>
                <p className="text-xs text-gray-400 mb-2">
                  Generated{" "}
                  {format(new Date(activeReport.created_at), "MMM d, yyyy HH:mm")}
                </p>
                <p className="text-sm text-gray-700 whitespace-pre-wrap">
                  {activeReport.narrative}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Past Reports */}
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">
            Past Reports
          </h3>
          {reportsLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="animate-pulse bg-gray-200 rounded h-12 w-full"
                />
              ))}
            </div>
          ) : pastReports.length === 0 ? (
            <p className="text-sm text-gray-400">No reports generated yet.</p>
          ) : (
            <div className="space-y-2">
              {pastReports.map((report) => {
                const isExpanded = expandedIds.has(report.id);
                const preview = (report.narrative ?? "").slice(0, 100);
                const hasMore = (report.narrative ?? "").length > 100;
                return (
                  <div
                    key={report.id}
                    className="rounded-lg border border-gray-200 p-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-gray-400 mb-1">
                          {format(
                            new Date(report.created_at),
                            "MMM d, yyyy HH:mm"
                          )}
                        </p>
                        <p className="text-sm text-gray-700">
                          {isExpanded
                            ? report.narrative
                            : preview + (hasMore && !isExpanded ? "…" : "")}
                        </p>
                      </div>
                      {hasMore && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="shrink-0 text-xs text-gray-500"
                          onClick={() => toggleExpand(report.id)}
                        >
                          {isExpanded ? "Collapse" : "Expand"}
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Page ───

export default function AnalyticsPage() {
  const { toast, showToast } = useToast();

  return (
    <div className="space-y-6">
      <ToastBanner toast={toast} />
      <h2 className="text-2xl font-bold text-gray-900">Analytics</h2>
      <ProcessMiningSection />
      <AnomaliesSection />
      <RootCauseReportSection onError={(msg) => showToast(msg, "error")} />
    </div>
  );
}
