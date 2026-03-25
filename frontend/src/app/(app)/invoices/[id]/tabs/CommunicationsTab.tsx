// ─── Communications Tab Component ───

import { Card, CardContent } from "@/components/ui/card";
import { format } from "date-fns";
import type { VendorMessage } from "../types";

// ─── Types ───

interface CommunicationsTabProps {
  messages: VendorMessage[];
  msgBody: string;
  msgMode: "internal" | "vendor";
  isSending: boolean;
  setMsgBody: (body: string) => void;
  setMsgMode: (mode: "internal" | "vendor") => void;
  onSend: () => void;
}

// ─── Component ───

export function CommunicationsTab({
  messages,
  msgBody,
  msgMode,
  isSending,
  setMsgBody,
  setMsgMode,
  onSend,
}: CommunicationsTabProps) {
  return (
    <Card>
      <CardContent className="pt-4 space-y-4">
        {/* Message thread */}
        <div className="space-y-3 max-h-[480px] overflow-y-auto pr-1">
          {messages.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-6">No messages yet.</p>
          )}
          {messages.map((msg) => {
            const isInbound = msg.direction === "inbound";
            const isInternal = msg.is_internal;
            const isRight = !isInternal && !isInbound;

            let bgClass = "bg-gray-100";
            let label = "Internal Note";
            if (!isInternal && !isInbound) {
              bgClass = "bg-blue-100";
              label = "Sent to Vendor";
            } else if (isInbound) {
              bgClass = "bg-green-100";
              label = "Vendor Reply";
            }

            return (
              <div key={msg.id} className={`flex ${isRight ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[70%] rounded-lg px-4 py-3 ${bgClass}`}>
                  <p className="text-xs font-semibold text-gray-600 mb-1">{label}</p>
                  <p className="text-sm text-gray-800 whitespace-pre-wrap">{msg.body}</p>
                  <p className="text-xs text-gray-400 mt-1.5">
                    {msg.sender_email || "System"} ·{" "}
                    {format(new Date(msg.created_at), "MMM d, yyyy HH:mm")}
                  </p>
                </div>
              </div>
            );
          })}
        </div>

        {/* Compose area */}
        <div className="border-t pt-4 space-y-3">
          {/* Mode toggle */}
          <div className="flex rounded-md border border-gray-200 w-fit">
            <button
              onClick={() => setMsgMode("vendor")}
              className={`px-3 py-1.5 text-sm rounded-l-md transition-colors ${
                msgMode === "vendor"
                  ? "bg-blue-600 text-white"
                  : "bg-white text-gray-600 hover:bg-gray-50"
              }`}
            >
              Send to Vendor
            </button>
            <button
              onClick={() => setMsgMode("internal")}
              className={`px-3 py-1.5 text-sm rounded-r-md transition-colors ${
                msgMode === "internal"
                  ? "bg-gray-600 text-white"
                  : "bg-white text-gray-600 hover:bg-gray-50"
              }`}
            >
              Internal Note
            </button>
          </div>

          <textarea
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
            rows={3}
            placeholder={msgMode === "internal" ? "Add an internal note..." : "Write a message to the vendor..."}
            value={msgBody}
            onChange={(e) => setMsgBody(e.target.value)}
          />

          <div className="flex justify-end">
            <button
              onClick={onSend}
              disabled={!msgBody.trim() || isSending}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {isSending && (
                <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
              )}
              Send
            </button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
