"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { format } from "date-fns";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";

// ─── Types ───

interface NotificationPrefs {
  email: { approval_request: boolean; fraud_alert: boolean; exception_created: boolean };
  slack: { approval_request: boolean; fraud_alert: boolean; exception_created: boolean };
  in_app: { approval_request: boolean; fraud_alert: boolean; exception_created: boolean };
}

interface EmailIngestionStatus {
  is_configured: boolean;
  last_poll_at: string | null;
  total_ingested: number;
}

interface GLClassifierStatus {
  model_version: string | null;
  accuracy: number | null;
  trained_at: string | null;
  training_samples: number | null;
  status: "ready" | "not_trained";
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

const CHANNELS = ["email", "slack", "in_app"] as const;
const EVENTS = ["approval_request", "fraud_alert", "exception_created"] as const;

const CHANNEL_LABELS: Record<typeof CHANNELS[number], string> = {
  email: "Email",
  slack: "Slack",
  in_app: "In-App",
};

const EVENT_LABELS: Record<typeof EVENTS[number], string> = {
  approval_request: "Approval Request",
  fraud_alert: "Fraud Alert",
  exception_created: "Exception Created",
};

// ─── Notification Prefs Section ───

function NotificationPrefsSection({ showToast }: { showToast: (msg: string, type: "success" | "error") => void }) {
  const queryClient = useQueryClient();

  const { data: prefs, isLoading } = useQuery<NotificationPrefs>({
    queryKey: ["notification-prefs"],
    queryFn: () => api.get("/users/me/notification-prefs").then((r) => r.data),
  });

  const [localPrefs, setLocalPrefs] = useState<NotificationPrefs | null>(null);

  useEffect(() => {
    if (prefs && !localPrefs) setLocalPrefs(prefs);
  }, [prefs, localPrefs]);

  const saveMutation = useMutation({
    mutationFn: (data: Partial<NotificationPrefs>) =>
      api.patch("/users/me/notification-prefs", data).then((r) => r.data),
    onSuccess: (data) => {
      queryClient.setQueryData(["notification-prefs"], data);
      setLocalPrefs(data);
      showToast("Notification preferences saved", "success");
    },
    onError: () => showToast("Failed to save preferences", "error"),
  });

  const handleToggle = (channel: typeof CHANNELS[number], event: typeof EVENTS[number]) => {
    if (!localPrefs) return;
    const updated = {
      ...localPrefs,
      [channel]: { ...localPrefs[channel], [event]: !localPrefs[channel][event] },
    };
    setLocalPrefs(updated);
  };

  const handleSave = () => {
    if (localPrefs) saveMutation.mutate(localPrefs);
  };

  if (isLoading || !localPrefs) {
    return <div className="text-sm text-gray-400 py-4">Loading preferences…</div>;
  }

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wide pb-3 pr-6">
                Event
              </th>
              {CHANNELS.map((ch) => (
                <th key={ch} className="text-center text-xs font-medium text-gray-500 uppercase tracking-wide pb-3 px-4">
                  {CHANNEL_LABELS[ch]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {EVENTS.map((ev) => (
              <tr key={ev}>
                <td className="py-3 pr-6 text-gray-700 font-medium">{EVENT_LABELS[ev]}</td>
                {CHANNELS.map((ch) => (
                  <td key={ch} className="py-3 px-4 text-center">
                    <input
                      type="checkbox"
                      checked={localPrefs[ch][ev]}
                      onChange={() => handleToggle(ch, ev)}
                      className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saveMutation.isPending} size="sm">
          {saveMutation.isPending ? "Saving…" : "Save Preferences"}
        </Button>
      </div>
    </div>
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

  const { data: glStatus, isLoading: glLoading } =
    useQuery<GLClassifierStatus>({
      queryKey: ["admin-gl-classifier-status"],
      queryFn: () =>
        api.get("/admin/gl-classifier/status").then((r) => r.data),
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

      <Card>
        <CardHeader>
          <CardTitle className="text-base">GL Classifier</CardTitle>
        </CardHeader>
        <CardContent>
          {glLoading ? (
            <div className="text-sm text-gray-400 py-4">Loading status…</div>
          ) : glStatus?.status === "not_trained" ? (
            <p className="text-sm text-gray-500">No model trained yet</p>
          ) : glStatus ? (
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
              <div className="rounded-lg border p-4">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                  Model Version
                </p>
                <p className="text-sm font-medium text-gray-800">
                  {glStatus.model_version ?? <span className="text-gray-400">—</span>}
                </p>
              </div>

              <div className="rounded-lg border p-4">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                  Accuracy
                </p>
                <p className="text-sm font-medium text-gray-800">
                  {glStatus.accuracy != null ? (
                    `${(glStatus.accuracy * 100).toFixed(1)}%`
                  ) : (
                    <span className="text-gray-400">—</span>
                  )}
                </p>
              </div>

              <div className="rounded-lg border p-4">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                  Last Retrain
                </p>
                <p className="text-sm font-medium text-gray-800">
                  {glStatus.trained_at ? (
                    format(new Date(glStatus.trained_at), "MMM d, yyyy HH:mm")
                  ) : (
                    <span className="text-gray-400">—</span>
                  )}
                </p>
              </div>

              <div className="rounded-lg border p-4">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                  Training Samples
                </p>
                <p className="text-sm font-medium text-gray-800">
                  {glStatus.training_samples != null ? (
                    glStatus.training_samples.toLocaleString()
                  ) : (
                    <span className="text-gray-400">—</span>
                  )}
                </p>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Notification Preferences</CardTitle>
        </CardHeader>
        <CardContent>
          <NotificationPrefsSection showToast={showToast} />
        </CardContent>
      </Card>
    </div>
  );
}
