"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { InboxIcon } from "lucide-react";
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
        <CardTitle className="text-base">Process Mining — Step Durations</CardTitle>
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
            <p className="text-sm">No process data yet — process some invoices to see step durations</p>
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
                  label={{ value: "Hours", position: "insideRight", offset: 10, fontSize: 11 }}
                />
                <YAxis
                  type="category"
                  dataKey="step"
                  width={155}
                  tick={{ fontSize: 11 }}
                />
                <Tooltip
                  formatter={(value: number | undefined, name: string | undefined) => [
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
                <Bar dataKey="p90_hours" name="P90" fill="#94a3b8" opacity={0.4} radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <div className="flex items-center gap-4 text-xs text-gray-500">
              <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-green-500" /> &lt; 24h (fast)</span>
              <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-yellow-400" /> 24–72h (normal)</span>
              <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-red-500" /> ≥ 72h (slow)</span>
              <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-slate-400 opacity-50" /> P90</span>
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
        <p className="text-sm font-semibold text-gray-900">{anomaly.vendor_name}</p>
        <p className="text-xs text-gray-500 mt-0.5">Period starting {anomaly.period}</p>
        <p className="text-xs text-gray-600 mt-1">
          Exception rate: <span className="font-medium">{(anomaly.exception_rate * 100).toFixed(1)}%</span>
        </p>
      </div>
      <div className="text-right space-y-1">
        <span
          className={`inline-block px-2 py-0.5 rounded text-xs font-bold ${
            isSpike ? "bg-red-100 text-red-700" : "bg-blue-100 text-blue-700"
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
          Vendor-windows with exception rate &gt; 2 std deviations from baseline (last 6 months)
        </p>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="animate-pulse bg-gray-200 rounded h-16 w-full" />
            ))}
          </div>
        ) : data.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-400">
            <InboxIcon className="h-10 w-10 mb-2" />
            <p className="text-sm">No anomalies detected in the last 6 months</p>
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

// ─── Page ───

export default function AnalyticsPage() {
  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">Analytics</h2>
      <ProcessMiningSection />
      <AnomaliesSection />
    </div>
  );
}
