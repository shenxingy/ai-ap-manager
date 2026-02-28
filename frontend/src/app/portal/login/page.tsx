"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function PortalLoginPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [error, setError] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = token.trim();
    if (!trimmed) {
      setError("Please paste your portal access token.");
      return;
    }
    localStorage.setItem("vendor_portal_token", trimmed);
    router.push("/portal/invoices");
  }

  return (
    <div className="max-w-md mx-auto mt-16">
      <div className="bg-white rounded-lg border shadow-sm p-8">
        <h1 className="text-2xl font-bold mb-2">Vendor Portal Login</h1>
        <p className="text-gray-600 mb-6 text-sm">
          Paste the portal access token from your invitation email.
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="token" className="block text-sm font-medium mb-1">
              Access Token
            </label>
            <textarea
              id="token"
              rows={4}
              className="w-full border rounded-md px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Paste your token here…"
              value={token}
              onChange={(e) => {
                setToken(e.target.value);
                setError("");
              }}
            />
          </div>
          {error && <p className="text-red-600 text-sm">{error}</p>}
          <button
            type="submit"
            className="w-full bg-blue-600 text-white rounded-md py-2 text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            Access Portal
          </button>
        </form>
      </div>
    </div>
  );
}
