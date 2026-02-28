"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Sparkles, Send } from "lucide-react";
import api from "@/lib/api";

// ─── Types ───

interface AskAiResult {
  answer: string;
  table?: Array<Record<string, unknown>>;
  sql?: string;
}

const SUGGESTED_QUERIES = [
  "Which vendors have the most exceptions this month?",
  "Show me invoices with fraud score above 40",
  "What is the average approval time by department?",
  "List overdue invoices by vendor",
];

// ─── Panel ───

export function AskAiPanel() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskAiResult | null>(null);
  const [showSql, setShowSql] = useState(false);

  const askMutation = useMutation({
    mutationFn: (q: string) =>
      api.post<AskAiResult>("/ask-ai", { question: q }).then((r) => r.data),
    onSuccess: (data) => {
      setResult(data);
      setShowSql(false);
    },
  });

  const handleSubmit = () => {
    const q = question.trim();
    if (!q) return;
    askMutation.mutate(q);
  };

  const handleSuggestion = (q: string) => {
    setQuestion(q);
    askMutation.mutate(q);
  };

  const handleReset = () => {
    setResult(null);
    setQuestion("");
    setShowSql(false);
    askMutation.reset();
  };

  const tableKeys =
    result?.table && result.table.length > 0
      ? Object.keys(result.table[0])
      : [];

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" title="Ask AI">
          <Sparkles className="h-5 w-5 text-purple-500" />
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-[420px] sm:w-[480px] flex flex-col">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-purple-500" />
            Ask AI
          </SheetTitle>
        </SheetHeader>

        <div className="flex flex-col flex-1 gap-4 mt-4 overflow-hidden">
          {/* Input area */}
          <div className="flex gap-2">
            <input
              type="text"
              className="flex-1 border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
              placeholder="Ask anything about your AP data…"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
              disabled={askMutation.isPending}
            />
            <Button
              size="icon"
              onClick={handleSubmit}
              disabled={!question.trim() || askMutation.isPending}
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>

          {/* Loading */}
          {askMutation.isPending && (
            <div className="text-sm text-gray-500 animate-pulse">
              Thinking…
            </div>
          )}

          {/* Error */}
          {askMutation.isError && (
            <div className="text-sm text-red-600 bg-red-50 rounded-md p-3">
              Failed to get a response. Please try again.
            </div>
          )}

          {/* Results */}
          {result && !askMutation.isPending && (
            <div className="flex flex-col gap-3 flex-1 overflow-auto">
              <button
                className="text-xs text-blue-600 hover:text-blue-800 self-start"
                onClick={handleReset}
              >
                ← New query
              </button>

              {/* Answer text */}
              <p className="text-sm text-gray-800 whitespace-pre-wrap">
                {result.answer}
              </p>

              {/* Table */}
              {result.table && result.table.length > 0 && (
                <div className="overflow-x-auto rounded-md border">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50">
                      <tr>
                        {tableKeys.map((k) => (
                          <th
                            key={k}
                            className="px-3 py-2 text-left font-medium text-gray-600 border-b"
                          >
                            {k}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.table.map((row, i) => (
                        <tr key={i} className="border-b last:border-0">
                          {tableKeys.map((k) => (
                            <td key={k} className="px-3 py-2 text-gray-700">
                              {String(row[k] ?? "—")}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* SQL reveal */}
              {result.sql && (
                <div>
                  <button
                    className="text-xs text-gray-400 hover:text-gray-600"
                    onClick={() => setShowSql((v) => !v)}
                  >
                    {showSql ? "Hide SQL" : "Show SQL"}
                  </button>
                  {showSql && (
                    <pre className="mt-2 text-xs bg-gray-900 text-green-400 p-3 rounded-md overflow-auto">
                      {result.sql}
                    </pre>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Suggestions (shown when no result) */}
          {!result && !askMutation.isPending && (
            <div className="flex flex-col gap-2">
              <p className="text-xs text-gray-500 font-medium">Suggested queries</p>
              {SUGGESTED_QUERIES.map((q) => (
                <button
                  key={q}
                  className="text-left text-sm px-3 py-2 rounded-md border border-gray-200 hover:bg-purple-50 hover:border-purple-200 text-gray-700 transition-colors"
                  onClick={() => handleSuggestion(q)}
                >
                  {q}
                </button>
              ))}
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
