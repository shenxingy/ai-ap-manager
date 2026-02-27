"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";

interface Toast {
  id: string;
  status: number;
  message: string;
}

export function ErrorToastListener() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    const handleApiError = (event: Event) => {
      const customEvent = event as CustomEvent<{ status: number; message: string }>;
      const { status, message } = customEvent.detail;
      const id = Math.random().toString(36).slice(2);
      const newToast = { id, status, message };

      setToasts((prev) => [...prev, newToast]);

      // Auto-remove after 3 seconds
      const timeout = setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 3000);

      return () => clearTimeout(timeout);
    };

    window.addEventListener("api-error", handleApiError);
    return () => window.removeEventListener("api-error", handleApiError);
  }, []);

  return (
    <div className="fixed bottom-4 right-4 space-y-2 z-50 max-w-sm">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className="flex items-center justify-between bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-800"
        >
          <span>{toast.message}</span>
          <button
            onClick={() => setToasts((prev) => prev.filter((t) => t.id !== toast.id))}
            className="ml-3 text-red-600 hover:text-red-800"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
