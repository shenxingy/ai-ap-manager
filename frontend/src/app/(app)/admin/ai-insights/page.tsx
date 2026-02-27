"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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
  rule_type: string;
  current_config: Record<string, unknown>;
  suggested_config: Record<string, unknown>;
  expected_impact: string;
  confidence: number;
  status: string;
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

function truncateJson(obj: Record<string, unknown>, maxLen = 60): string {
  const s = JSON.stringify(obj);
  return s.length > maxLen ? s.slice(0, maxLen) + "…" : s;
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

// ─── Confidence Badge ───

function ConfidenceBadge({ confidence }: { confidence: number }) {
  if (confidence >= 0.7) {
    return (
      <Badge className="bg-green-100 text-green-700 hover:bg-green-100">
        {(confidence * 100).toFixed(0)}%
      </Badge>
    );
  }
  if (confidence >= 0.5) {
    return (
      <Badge className="bg-yellow-100 text-yellow-700 hover:bg-yellow-100">
        {(confidence * 100).toFixed(0)}%
      </Badge>
    );
  }
  return (
    <Badge className="bg-red-100 text-red-700 hover:bg-red-100">
      {(confidence * 100).toFixed(0)}%
    </Badge>
  );
}

// ─── Value Chip ───

function ValueChip({ value }: { value: number | string }) {
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono bg-gray-100 text-gray-700">
      {String(value)}
    </span>
  );
}

// ─── Correction Stats Card ───

function CorrectionStatsCard({
  total,
  isLoading,
}: {
  total: number;
  isLoading: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Correction Stats</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="animate-pulse bg-gray-200 rounded h-8 w-48" />
        ) : (
          <p className="text-2xl font-bold text-gray-900">
            {total}{" "}
            <span className="text-sm font-normal text-gray-500">
              pending rule recommendation{total !== 1 ? "s" : ""}
            </span>
          </p>
        )}
      </CardContent>
    </Card>
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
    queryKey: ["rule-recommendations", "pending"],
    queryFn: () =>
      api
        .get("/admin/rule-recommendations?status=pending")
        .then((r) => r.data),
    retry: false,
  });

  const acceptMutation = useMutation({
    mutationFn: (id: string) =>
      api
        .post(`/admin/rule-recommendations/${id}/accept`)
        .then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rule-recommendations"] });
      onSuccess("Recommendation accepted");
    },
    onError: (err) => onError(extractApiError(err)),
  });

  const rejectMutation = useMutation({
    mutationFn: (id: string) =>
      api
        .post(`/admin/rule-recommendations/${id}/reject`)
        .then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rule-recommendations"] });
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
            <svg
              className="h-5 w-5 text-gray-400 shrink-0"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            No recommendations yet. Corrections are analyzed weekly.
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <CorrectionStatsCard
        total={data?.total ?? 0}
        isLoading={isLoading}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Rule Recommendations</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Rule Type</TableHead>
                <TableHead>Current Config</TableHead>
                <TableHead>Suggested Config</TableHead>
                <TableHead>Expected Impact</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead className="w-36" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="text-center text-gray-400 py-8"
                  >
                    Loading…
                  </TableCell>
                </TableRow>
              )}
              {!isLoading && !error && recommendations.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="text-center text-gray-400 py-8"
                  >
                    No recommendations yet. Corrections are analyzed weekly.
                  </TableCell>
                </TableRow>
              )}
              {recommendations.map((rec) => (
                <TableRow key={rec.id}>
                  <TableCell>
                    <p className="font-medium text-sm">{rec.rule_type}</p>
                  </TableCell>
                  <TableCell>
                    <span className="text-xs font-mono text-gray-600">
                      {truncateJson(rec.current_config)}
                    </span>
                  </TableCell>
                  <TableCell>
                    <span className="text-xs font-mono text-gray-600">
                      {truncateJson(rec.suggested_config)}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-gray-600 max-w-xs">
                    <p className="line-clamp-2">{rec.expected_impact}</p>
                  </TableCell>
                  <TableCell>
                    <ConfidenceBadge confidence={rec.confidence} />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-red-600 border-red-200 hover:bg-red-50 text-xs"
                        disabled={
                          rejectMutation.isPending || acceptMutation.isPending
                        }
                        onClick={() => rejectMutation.mutate(rec.id)}
                      >
                        Reject
                      </Button>
                      <Button
                        size="sm"
                        className="text-xs"
                        disabled={
                          acceptMutation.isPending || rejectMutation.isPending
                        }
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
    </>
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
            <svg
              className="h-5 w-5 text-gray-400 shrink-0"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
              />
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
                <TableCell
                  colSpan={6}
                  className="text-center text-gray-400 py-8"
                >
                  Loading…
                </TableCell>
              </TableRow>
            )}
            {!isLoading && !error && logs.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={6}
                  className="text-center text-gray-400 py-8"
                >
                  No overrides recorded yet.
                </TableCell>
              </TableRow>
            )}
            {logs.map((log) => (
              <TableRow key={log.id}>
                <TableCell className="text-sm font-mono text-gray-600">
                  {log.invoice_id.slice(0, 8)}…
                </TableCell>
                <TableCell className="text-sm text-gray-700">
                  {log.field}
                </TableCell>
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
              <span>
                Page {page} of {totalPages}
              </span>
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
  const { user } = useAuthStore();
  const router = useRouter();

  useEffect(() => {
    if (user && user.role !== "ADMIN") {
      router.push("/unauthorized");
    }
  }, [user, router]);

  const { toast, showToast } = useToast();

  return (
    <div className="space-y-6">
      <ToastBanner toast={toast} />

      <div>
        <h2 className="text-2xl font-bold text-gray-900">AI Insights</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          System-learned corrections and rule recommendations
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
