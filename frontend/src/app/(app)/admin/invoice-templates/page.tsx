"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth";
import api from "@/lib/api";
import { format } from "date-fns";

// ─── Types ───

interface InvoiceTemplate {
  id: string;
  vendor_id: string;
  name: string;
  default_po_id: string | null;
  created_at: string;
}

// ─── Page ───

export default function InvoiceTemplatesPage() {
  const router = useRouter();
  const { user } = useAuthStore();

  useEffect(() => {
    if (user && user.role !== "ADMIN" && user.role !== "AP_ANALYST") {
      router.push("/unauthorized");
    }
  }, [user, router]);

  const { data: templates = [], isLoading } = useQuery<InvoiceTemplate[]>({
    queryKey: ["invoice-templates"],
    queryFn: async () => {
      const res = await api.get<InvoiceTemplate[]>("/admin/invoice-templates");
      return res.data;
    },
  });

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">
          Invoice Templates
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Reusable templates that pre-populate new invoices with vendor defaults.
        </p>
      </div>

      <div className="rounded-lg border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600">
                Name
              </th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">
                Vendor ID
              </th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">
                Default PO
              </th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">
                Created At
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading ? (
              <tr>
                <td
                  colSpan={4}
                  className="px-4 py-8 text-center text-gray-400"
                >
                  Loading…
                </td>
              </tr>
            ) : templates.length === 0 ? (
              <tr>
                <td
                  colSpan={4}
                  className="px-4 py-8 text-center text-gray-400"
                >
                  No templates yet
                </td>
              </tr>
            ) : (
              templates.map((t) => (
                <tr key={t.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-900">
                    {t.name}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-500">
                    {t.vendor_id}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-500">
                    {t.default_po_id ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {format(new Date(t.created_at), "MMM d, yyyy")}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
