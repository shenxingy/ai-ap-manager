// ─── Exceptions Tab Component ───

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { format } from "date-fns";
import type { ExceptionItem } from "../types";

// ─── Types ───

interface ExceptionsTabProps {
  exceptions: ExceptionItem[];
}

// ─── Component ───

export function ExceptionsTab({ exceptions }: ExceptionsTabProps) {
  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Code</TableHead>
              <TableHead>Severity</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>Raised At</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {exceptions.map((ex) => (
              <TableRow key={ex.id}>
                <TableCell className="font-mono text-xs">{ex.code}</TableCell>
                <TableCell>
                  <Badge variant={ex.severity === "HIGH" ? "destructive" : "secondary"}>
                    {ex.severity}
                  </Badge>
                </TableCell>
                <TableCell>{ex.status}</TableCell>
                <TableCell>{ex.description}</TableCell>
                <TableCell className="text-sm text-gray-500">
                  {format(new Date(ex.created_at), "MMM d, yyyy")}
                </TableCell>
              </TableRow>
            ))}
            {exceptions.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-gray-400 py-6">
                  No exceptions.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
