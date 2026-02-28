"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

interface PortalInvoice {
  id: number;
  invoice_number: string;
  status: string;
  total_amount: number;
  currency: string;
  due_date: string | null;
}

interface PaginatedResponse {
  items: PortalInvoice[];
  total: number;
}

const PAGE_SIZE = 20;

export default function PortalInvoicesPage() {
  const router = useRouter();
  const [invoices, setInvoices] = useState<PortalInvoice[]>([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = localStorage.getItem("vendor_portal_token");
    if (!token) {
      router.push("/portal/login");
      return;
    }

    async function fetchInvoices() {
      setLoading(true);
      setError("");
      try {
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/portal/invoices?skip=${skip}&limit=${PAGE_SIZE}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        if (res.status === 401) {
          router.push("/portal/login");
          return;
        }
        if (!res.ok) {
          setError("Failed to load invoices.");
          return;
        }
        const data: PaginatedResponse = await res.json();
        setInvoices(data.items ?? []);
        setTotal(data.total ?? 0);
      } catch {
        setError("Network error. Please try again.");
      } finally {
        setLoading(false);
      }
    }

    fetchInvoices();
  }, [router, skip]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(skip / PAGE_SIZE) + 1;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">My Invoices</h1>

      {loading && <p className="text-gray-500">Loading…</p>}
      {error && <p className="text-red-600">{error}</p>}

      {!loading && !error && (
        <>
          <div className="bg-white rounded-lg border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-gray-700">Invoice #</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-700">Status</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-700">Amount</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-700">Currency</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-700">Due Date</th>
                </tr>
              </thead>
              <tbody>
                {invoices.length === 0 && (
                  <tr>
                    <td colSpan={5} className="text-center py-8 text-gray-400">
                      No invoices found.
                    </td>
                  </tr>
                )}
                {invoices.map((inv) => (
                  <tr
                    key={inv.id}
                    className="border-t hover:bg-gray-50 cursor-pointer"
                    onClick={() => router.push(`/portal/invoices/${inv.id}`)}
                  >
                    <td className="px-4 py-3 font-mono text-blue-600">{inv.invoice_number}</td>
                    <td className="px-4 py-3">
                      <span className="capitalize px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-700">
                        {inv.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {inv.total_amount?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="px-4 py-3">{inv.currency}</td>
                    <td className="px-4 py-3">{inv.due_date ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4 text-sm text-gray-600">
              <span>
                Page {currentPage} of {totalPages} ({total} total)
              </span>
              <div className="flex gap-2">
                <button
                  disabled={skip === 0}
                  onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))}
                  className="px-3 py-1 border rounded disabled:opacity-40 hover:bg-gray-100"
                >
                  Previous
                </button>
                <button
                  disabled={skip + PAGE_SIZE >= total}
                  onClick={() => setSkip(skip + PAGE_SIZE)}
                  className="px-3 py-1 border rounded disabled:opacity-40 hover:bg-gray-100"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
