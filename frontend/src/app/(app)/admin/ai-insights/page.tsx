"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { format } from "date-fns";
import api from "@/lib/api";

// ─── Types ───

interface RuleRecommendation {
  id: string;
  rule_id: string;
  rule_name: string;
  field: string;
  current_value: number | string;
  suggested_value: number | string;
  override_count: number;
  reasoning: string;
  created_at: string;
}

interface OverrideLog {
  id: string;
  invoice_id: string;
  field: string;
  original_value: number | string;
  overridden_value: number | string;
  overridden_by: string;
  reason: string | null;
  created_at: string;
}

interface RecommendationListResponse {
  items: RuleRecommendation[];
  total: number;
}

interface OverrideLogListResponse {
  items: OverrideLog[];
  total: number;
}

// ─── Helpers ───

function extractApiError(err: unknown): string {
  return (
    (err as { response?: { data?: { detail?: string } } })?.response?.data
      ?.detail ?? "Operation failed"
  );
}

function isNotFound(err: unknown): boolean {
  return (err as { response?: { status?: number } })?.response?.status === 404;
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

// ─── Value Display ───

function ValueChip({ value }: { value: number | string }) {
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono bg-gray-100 text-gray-700">
      {String(value)}
    </span>
  );
}

// ─── Recommendations Section ───

function RecommendationsSection({
  onSuccess,
  onError,
}: {
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}) {
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery<RecommendationListResponse>({
    queryKey: ["admin-rule-recommendations"],
    queryFn: () =>
      api.get("/admin/rule-recommendations").then((r) => r.data),
    retry: false,
  });

  const acceptMutation = useMutation({
    mutationFn: (id: string) =>
      api.post(`/admin/rule-recommendations/${id}/accept`).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-rule-recommendations"] });
      onSuccess("Recommendation accepted");
    },
    onError: (err) => onError(extractApiError(err)),
  });

  const rejectMutation = useMutation({
    mutationFn: (id: string) =>
      api.post(`/admin/rule-recommendations/${id}/reject`).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-rule-recommendations"] });
      onSuccess("Recommendation rejected");
    },
    onError: (err) => onError(extractApiError(err)),
  });

  const recommendations = data?.items ?? [];

  if (error && isNotFound(error)) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Rule Recommendations</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3 rounded-lg bg-gray-50 border border-dashed p-6 text-sm text-gray-500">
            <svg className="h-5 w-5 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            AI rule recommendations are not yet available. They will appear here once the AI engine has analyzed enough override patterns.
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Rule Recommendations</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Rule / Field</TableHead>
              <TableHead>Current → Suggested</TableHead>
              <TableHead>Overrides</TableHead>
              <TableHead>Reasoning</TableHead>
              <TableHead className="w-36" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-gray-400 py-8">
                  Loading…
                </TableCell>
              </TableRow>
            )}
            {!isLoading && !error && recommendations.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-gray-400 py-8">
                  No recommendations at this time.
                </TableCell>
              </TableRow>
            )}
            {recommendations.map((rec) => (
              <TableRow key={rec.id}>
                <TableCell>
                  <p className="font-medium text-sm">{rec.rule_name}</p>
                  <p className="text-xs text-gray-500">{rec.field}</p>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1.5 text-xs">
                    <ValueChip value={rec.current_value} />
                    <span className="text-gray-400">→</span>
                    <ValueChip value={rec.suggested_value} />
                  </div>
                </TableCell>
                <TableCell>
                  <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-orange-100 text-orange-700">
                    {rec.override_count}×
                  </span>
                </TableCell>
                <TableCell className="text-sm text-gray-600 max-w-xs">
                  <p className="line-clamp-2">{rec.reasoning}</p>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-red-600 border-red-200 hover:bg-red-50 text-xs"
                      disabled={rejectMutation.isPending || acceptMutation.isPending}
                      onClick={() => rejectMutation.mutate(rec.id)}
                    >
                      Reject
                    </Button>
                    <Button
                      size="sm"
                      className="text-xs"
                      disabled={acceptMutation.isPending || rejectMutation.isPending}
                      onClick={() => acceptMutation.mutate(rec.id)}
                    >
                      Accept
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// ─── Override History Section ───

function OverrideHistorySection() {
  const [page, setPage] = useState(1);

  const { data, isLoading, error } = useQuery<OverrideLogListResponse>({
    queryKey: ["admin-override-logs", page],
    queryFn: () =>
      api
        .get(`/admin/override-logs?skip=${(page - 1) * 20}&limit=20`)
        .then((r) => r.data),
    retry: false,
  });

  const logs = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / 20) || 1;

  if (error && isNotFound(error)) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Override History</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3 rounded-lg bg-gray-50 border border-dashed p-6 text-sm text-gray-500">
            <svg className="h-5 w-5 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Override history coming soon.
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Override History</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Invoice</TableHead>
              <TableHead>Field</TableHead>
              <TableHead>Original → Override</TableHead>
              <TableHead>By</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Date</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-gray-400 py-8">
                  Loading…
                </TableCell>
              </TableRow>
            )}
            {!isLoading && !error && logs.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-gray-400 py-8">
                  No overrides recorded yet.
                </TableCell>
              </TableRow>
            )}
            {logs.map((log) => (
              <TableRow key={log.id}>
                <TableCell className="text-sm font-mono text-gray-600">
                  {log.invoice_id.slice(0, 8)}…
                </TableCell>
                <TableCell className="text-sm text-gray-700">{log.field}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-1.5 text-xs">
                    <ValueChip value={log.original_value} />
                    <span className="text-gray-400">→</span>
                    <ValueChip value={log.overridden_value} />
                  </div>
                </TableCell>
                <TableCell className="text-sm text-gray-600">
                  {log.overridden_by}
                </TableCell>
                <TableCell className="text-sm text-gray-500 max-w-xs">
                  {log.reason ?? <span className="text-gray-300">—</span>}
                </TableCell>
                <TableCell className="text-sm text-gray-500">
                  {format(new Date(log.created_at), "MMM d, yyyy")}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>

        {totalPages > 1 && (
          <div className="flex items-center justify-between text-sm text-gray-600 px-4 py-3 border-t">
            <span>{total} total overrides</span>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </Button>
              <span>Page {page} of {totalPages}</span>
              <Button
                size="sm"
                variant="outline"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Page ───

export default function AdminAIInsightsPage() {
  const { toast, showToast } = useToast();

  return (
    <div className="space-y-6">
      <ToastBanner toast={toast} />

      <div>
        <h2 className="text-2xl font-bold text-gray-900">AI Insights</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          AI-generated rule recommendations and override audit trail
        </p>
      </div>

      <RecommendationsSection
        onSuccess={(msg) => showToast(msg, "success")}
        onError={(msg) => showToast(msg, "error")}
      />

      <OverrideHistorySection />
    </div>
  );
}
