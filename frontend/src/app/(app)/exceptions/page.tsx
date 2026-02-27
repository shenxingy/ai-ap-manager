"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { format } from "date-fns";
import api from "@/lib/api";
import Link from "next/link";

// ─── Types ───

interface Exception {
  id: string;
  code: string;
  severity: string;
  status: string;
  description: string;
  assigned_to: string | null;
  invoice_id: string;
  invoice_number: string | null;
  created_at: string;
}

interface Comment {
  id: string;
  author: string;
  body: string;
  created_at: string;
}

// ─── Exception Detail Sheet ───

function ExceptionSheet({
  exception,
  onClose,
}: {
  exception: Exception | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [comment, setComment] = useState("");
  const [newStatus, setNewStatus] = useState<string | null>(null);

  const { data: comments = [] } = useQuery<Comment[]>({
    queryKey: ["exception-comments", exception?.id],
    queryFn: () => api.get(`/exceptions/${exception!.id}/comments`).then((r) => r.data),
    enabled: !!exception,
  });

  const submitComment = useMutation({
    mutationFn: (body: string) =>
      api.post(`/exceptions/${exception!.id}/comments`, { body }),
    onSuccess: () => {
      setComment("");
      queryClient.invalidateQueries({ queryKey: ["exception-comments", exception?.id] });
    },
  });

  const updateStatus = useMutation({
    mutationFn: (status: string) =>
      api.patch(`/exceptions/${exception!.id}`, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["exceptions"] });
    },
  });

  return (
    <Sheet open={!!exception} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-[480px] sm:w-[540px] flex flex-col">
        {exception && (
          <>
            <SheetHeader>
              <SheetTitle className="font-mono text-sm">{exception.code}</SheetTitle>
            </SheetHeader>

            <div className="mt-4 space-y-3 text-sm">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant={exception.severity === "HIGH" ? "destructive" : "secondary"}>
                  {exception.severity}
                </Badge>
                <Badge variant="outline">{exception.status}</Badge>
                <Link
                  href={`/invoices/${exception.invoice_id}`}
                  className="text-blue-600 hover:underline"
                >
                  Invoice {exception.invoice_number || exception.invoice_id.slice(0, 8)}
                </Link>
              </div>
              <p className="text-gray-600">{exception.description}</p>
              {exception.assigned_to && (
                <p className="text-gray-500">Assigned to: {exception.assigned_to}</p>
              )}

              {/* Status update */}
              <div className="flex items-center gap-2">
                <Select
                  value={newStatus ?? exception.status}
                  onValueChange={(v) => setNewStatus(v)}
                >
                  <SelectTrigger className="w-40">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {["OPEN", "IN_REVIEW", "RESOLVED", "WAIVED"].map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!newStatus || newStatus === exception.status}
                  onClick={() => newStatus && updateStatus.mutate(newStatus)}
                >
                  Update
                </Button>
              </div>
            </div>

            {/* Comments */}
            <div className="mt-6 flex-1 flex flex-col min-h-0">
              <h4 className="text-sm font-semibold mb-3">Comments</h4>
              <div className="flex-1 overflow-y-auto space-y-3 pr-1">
                {comments.map((c) => (
                  <div key={c.id} className="bg-gray-50 rounded-lg px-3 py-2">
                    <p className="text-xs text-gray-500 mb-1">
                      {c.author} · {format(new Date(c.created_at), "MMM d, HH:mm")}
                    </p>
                    <p className="text-sm">{c.body}</p>
                  </div>
                ))}
                {comments.length === 0 && (
                  <p className="text-sm text-gray-400">No comments yet.</p>
                )}
              </div>
              <div className="mt-3 flex gap-2">
                <textarea
                  className="flex-1 border rounded-md px-3 py-2 text-sm resize-none"
                  rows={2}
                  placeholder="Add a comment..."
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                />
                <Button
                  size="sm"
                  disabled={!comment.trim()}
                  onClick={() => submitComment.mutate(comment)}
                >
                  Post
                </Button>
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

// ─── Page ───

export default function ExceptionsPage() {
  const [selected, setSelected] = useState<Exception | null>(null);

  const { data: exceptions = [] } = useQuery<Exception[]>({
    queryKey: ["exceptions"],
    queryFn: () => api.get("/exceptions").then((r) => r.data),
  });

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold text-gray-900">Exceptions</h2>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead>
                <TableHead>Severity</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Assigned To</TableHead>
                <TableHead>Invoice</TableHead>
                <TableHead>Raised At</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {exceptions.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-gray-400 py-8">
                    No exceptions found.
                  </TableCell>
                </TableRow>
              )}
              {exceptions.map((ex) => (
                <TableRow
                  key={ex.id}
                  className="cursor-pointer hover:bg-gray-50"
                  onClick={() => setSelected(ex)}
                >
                  <TableCell className="font-mono text-xs">{ex.code}</TableCell>
                  <TableCell>
                    <Badge variant={ex.severity === "HIGH" ? "destructive" : "secondary"}>
                      {ex.severity}
                    </Badge>
                  </TableCell>
                  <TableCell>{ex.status}</TableCell>
                  <TableCell>{ex.assigned_to || "—"}</TableCell>
                  <TableCell>
                    <Link
                      href={`/invoices/${ex.invoice_id}`}
                      className="text-blue-600 hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {ex.invoice_number || ex.invoice_id.slice(0, 8)}
                    </Link>
                  </TableCell>
                  <TableCell className="text-sm text-gray-500">
                    {format(new Date(ex.created_at), "MMM d, yyyy")}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <ExceptionSheet exception={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
