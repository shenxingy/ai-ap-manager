"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { format } from "date-fns";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";

// ─── Types ───

interface EmailIngestionStatus {
  is_configured: boolean;
  last_poll_at: string | null;
  total_ingested: number;
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

// ─── Status Badge ───

function ConfiguredBadge({ configured }: { configured: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${
        configured
          ? "bg-green-100 text-green-700"
          : "bg-red-100 text-red-700"
      }`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${
          configured ? "bg-green-500" : "bg-red-500"
        }`}
      />
      {configured ? "Configured" : "Not Configured"}
    </span>
  );
}

// ─── Page ───

export default function AdminSettingsPage() {
  const { user } = useAuthStore();
  const router = useRouter();

  useEffect(() => {
    if (user && user.role !== "ADMIN") {
      router.push("/unauthorized");
    }
  }, [user, router]);

  const { toast, showToast } = useToast();

  const {
    data: status,
    isLoading,
    error,
    refetch,
  } = useQuery<EmailIngestionStatus>({
    queryKey: ["admin-email-ingestion-status"],
    queryFn: () =>
      api.get("/admin/email-ingestion/status").then((r) => r.data),
    retry: false,
  });

  const triggerPoll = useMutation({
    mutationFn: () =>
      api.post("/admin/email-ingestion/trigger").then((r) => r.data),
    onSuccess: () => {
      showToast("Poll triggered successfully", "success");
      refetch();
    },
    onError: () => showToast("Failed to trigger poll", "error"),
  });

  return (
    <div className="space-y-6">
      <ToastBanner toast={toast} />

      <div>
        <h2 className="text-2xl font-bold text-gray-900">Settings</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Email ingestion configuration and controls
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Email Ingestion</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="text-sm text-gray-400 py-4">Loading status…</div>
          ) : error ? (
            <div className="space-y-4">
              <div className="rounded-lg bg-amber-50 border border-amber-200 p-4 text-sm text-amber-700">
                Email ingestion status is unavailable. The feature may not be
                configured yet.
              </div>
              <Button
                onClick={() => triggerPoll.mutate()}
                disabled={triggerPoll.isPending}
                variant="outline"
              >
                {triggerPoll.isPending ? "Triggering…" : "Trigger Poll"}
              </Button>
            </div>
          ) : status ? (
            <div className="space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="rounded-lg border p-4">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                    Status
                  </p>
                  <ConfiguredBadge configured={status.is_configured} />
                </div>

                <div className="rounded-lg border p-4">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                    Last Poll
                  </p>
                  <p className="text-sm font-medium text-gray-800">
                    {status.last_poll_at ? (
                      format(new Date(status.last_poll_at), "MMM d, yyyy HH:mm")
                    ) : (
                      <span className="text-gray-400">Never</span>
                    )}
                  </p>
                </div>

                <div className="rounded-lg border p-4">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                    Total Ingested
                  </p>
                  <p className="text-sm font-medium text-gray-800">
                    {status.total_ingested.toLocaleString()} invoices
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <Button
                  onClick={() => triggerPoll.mutate()}
                  disabled={triggerPoll.isPending}
                >
                  {triggerPoll.isPending ? "Triggering…" : "Trigger Poll"}
                </Button>
                <p className="text-xs text-gray-400">
                  Manually trigger an email inbox scan for new invoices
                </p>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
