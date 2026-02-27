"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import api from "@/lib/api";

// ─── Types ───

interface KpiSummary {
  touchless_rate: number;
  exception_rate: number;
  avg_cycle_time_hours: number;
  total_received: number;
}

interface KpiTrendPoint {
  date: string;
  touchless_rate: number;
  exception_rate: number;
}

// ─── KPI Card ───

function KpiCard({ title, value, unit }: { title: string; value: number | string; unit?: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-gray-500">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-bold">
          {value}
          {unit && <span className="text-lg font-medium text-gray-400 ml-1">{unit}</span>}
        </p>
      </CardContent>
    </Card>
  );
}

// ─── Page ───

export default function DashboardPage() {
  const [period, setPeriod] = useState("30");

  const { data: summary } = useQuery<KpiSummary>({
    queryKey: ["kpi-summary", period],
    queryFn: () => api.get(`/kpi/summary?period_days=${period}`).then((r) => r.data),
    refetchInterval: 5 * 60 * 1000,
  });

  const { data: trends = [] } = useQuery<KpiTrendPoint[]>({
    queryKey: ["kpi-trends", period],
    queryFn: () => api.get(`/kpi/trends?period_days=${period}`).then((r) => r.data),
    refetchInterval: 5 * 60 * 1000,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-900">Dashboard</h2>
        <Select value={period} onValueChange={setPeriod}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="Period" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7">Last 7 days</SelectItem>
            <SelectItem value="30">Last 30 days</SelectItem>
            <SelectItem value="90">Last 90 days</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          title="Touchless Rate"
          value={summary ? `${(summary.touchless_rate * 100).toFixed(1)}` : "—"}
          unit="%"
        />
        <KpiCard
          title="Exception Rate"
          value={summary ? `${(summary.exception_rate * 100).toFixed(1)}` : "—"}
          unit="%"
        />
        <KpiCard
          title="Avg Cycle Time"
          value={summary ? `${summary.avg_cycle_time_hours.toFixed(1)}` : "—"}
          unit="hrs"
        />
        <KpiCard
          title="Total Received"
          value={summary ? summary.total_received.toLocaleString() : "—"}
        />
      </div>

      {/* Trends Chart */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Trends</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={trends} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v: number | undefined) => v != null ? `${(v * 100).toFixed(1)}%` : "—"} />
              <Legend />
              <Line
                type="monotone"
                dataKey="touchless_rate"
                name="Touchless Rate"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="exception_rate"
                name="Exception Rate"
                stroke="#ef4444"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}
