"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";

interface PortalInvoiceDetail {
  id: number;
  invoice_number: string;
  status: string;
  total_amount: number;
  currency: string;
  invoice_date: string | null;
  due_date: string | null;
}

const DISPUTE_REASONS = [
  { value: "incorrect_amount", label: "Incorrect Amount" },
  { value: "duplicate", label: "Duplicate Invoice" },
  { value: "already_paid", label: "Already Paid" },
  { value: "other", label: "Other" },
];

export default function PortalInvoiceDetailPage() {
  const router = useRouter();
  const params = useParams();
  const invoiceId = params.id as string;

  const [invoice, setInvoice] = useState<PortalInvoiceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Dispute modal state
  const [showModal, setShowModal] = useState(false);
  const [disputeReason, setDisputeReason] = useState("incorrect_amount");
  const [disputeDescription, setDisputeDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("vendor_portal_token");
    if (!token) {
      router.push("/portal/login");
      return;
    }

    async function fetchInvoice() {
      setLoading(true);
      setError("");
      try {
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/portal/invoices/${invoiceId}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        if (res.status === 401) {
          router.push("/portal/login");
          return;
        }
        if (!res.ok) {
          setError("Failed to load invoice.");
          return;
        }
        const data: PortalInvoiceDetail = await res.json();
        setInvoice(data);
      } catch {
        setError("Network error. Please try again.");
      } finally {
        setLoading(false);
      }
    }

    fetchInvoice();
  }, [router, invoiceId]);

  async function handleDisputeSubmit(e: React.FormEvent) {
    e.preventDefault();
    const token = localStorage.getItem("vendor_portal_token");
    if (!token) {
      router.push("/portal/login");
      return;
    }
    setSubmitting(true);
    setSubmitError("");
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/portal/invoices/${invoiceId}/dispute`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ reason: disputeReason, description: disputeDescription }),
        }
      );
      if (!res.ok) {
        setSubmitError("Failed to submit dispute. Please try again.");
        return;
      }
      setSubmitted(true);
      setShowModal(false);
    } catch {
      setSubmitError("Network error. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  function openModal() {
    setDisputeReason("incorrect_amount");
    setDisputeDescription("");
    setSubmitError("");
    setShowModal(true);
  }

  return (
    <div className="max-w-2xl">
      <Link href="/portal/invoices" className="text-sm text-blue-600 hover:underline mb-6 block">
        ← Back to Invoices
      </Link>

      {loading && <p className="text-gray-500">Loading…</p>}
      {error && <p className="text-red-600">{error}</p>}

      {!loading && !error && invoice && (
        <>
          <div className="bg-white rounded-lg border shadow-sm p-6 mb-4">
            <h1 className="text-2xl font-bold mb-6">Invoice {invoice.invoice_number}</h1>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm">
              <div>
                <dt className="text-gray-500 mb-1">Status</dt>
                <dd>
                  <span className="capitalize px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-700">
                    {invoice.status}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-gray-500 mb-1">Currency</dt>
                <dd className="font-medium">{invoice.currency}</dd>
              </div>
              <div>
                <dt className="text-gray-500 mb-1">Total Amount</dt>
                <dd className="font-medium text-lg">
                  {invoice.total_amount?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500 mb-1">Invoice Date</dt>
                <dd className="font-medium">{invoice.invoice_date ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-gray-500 mb-1">Due Date</dt>
                <dd className="font-medium">{invoice.due_date ?? "—"}</dd>
              </div>
            </dl>
          </div>

          {submitted && (
            <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-green-800 text-sm mb-4">
              Your dispute has been submitted successfully. Our team will review it and contact you.
            </div>
          )}

          {!submitted && (
            <button
              onClick={openModal}
              className="bg-red-600 text-white rounded-md px-4 py-2 text-sm font-medium hover:bg-red-700 transition-colors"
            >
              Submit Dispute
            </button>
          )}
        </>
      )}

      {/* Dispute Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6">
            <h2 className="text-lg font-bold mb-4">Submit Dispute</h2>
            <form onSubmit={handleDisputeSubmit} className="space-y-4">
              <div>
                <label htmlFor="reason" className="block text-sm font-medium mb-1">
                  Reason
                </label>
                <select
                  id="reason"
                  value={disputeReason}
                  onChange={(e) => setDisputeReason(e.target.value)}
                  className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {DISPUTE_REASONS.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="description" className="block text-sm font-medium mb-1">
                  Description
                </label>
                <textarea
                  id="description"
                  rows={4}
                  required
                  value={disputeDescription}
                  onChange={(e) => setDisputeDescription(e.target.value)}
                  className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Please describe the issue in detail…"
                />
              </div>
              {submitError && <p className="text-red-600 text-sm">{submitError}</p>}
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-sm border rounded-md hover:bg-gray-50"
                  disabled={submitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50"
                >
                  {submitting ? "Submitting…" : "Submit Dispute"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
