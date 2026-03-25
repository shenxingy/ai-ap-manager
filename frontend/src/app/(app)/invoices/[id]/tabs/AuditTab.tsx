// ─── Audit Tab Component ───

import { Card, CardContent } from "@/components/ui/card";
import { format } from "date-fns";
import type { AuditEntry } from "../types";

// ─── Types ───

interface AuditTabProps {
  auditLog: AuditEntry[];
}

// ─── Component ───

export function AuditTab({ auditLog }: AuditTabProps) {
  return (
    <Card>
      <CardContent className="pt-4">
        <ol className="relative border-l border-gray-200 space-y-4 ml-3">
          {auditLog.map((entry) => (
            <li key={entry.id} className="ml-4">
              <div className="absolute w-2.5 h-2.5 bg-gray-400 rounded-full mt-1 -left-1.5 border border-white" />
              <p className="text-sm font-medium text-gray-900">{entry.action}</p>
              <p className="text-xs text-gray-500">
                {entry.actor} · {format(new Date(entry.created_at), "MMM d, yyyy HH:mm")}
              </p>
              {entry.detail && (
                <p className="text-xs text-gray-400 mt-0.5">{entry.detail}</p>
              )}
            </li>
          ))}
          {auditLog.length === 0 && (
            <li className="ml-4 text-sm text-gray-400">No audit entries.</li>
          )}
        </ol>
      </CardContent>
    </Card>
  );
}
