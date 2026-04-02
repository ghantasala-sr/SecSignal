"use client";

import { useState } from "react";
import { ArrowUp, Square } from "lucide-react";

interface QueryInputProps {
  onSubmit: (query: string) => void;
  onCancel?: () => void;
  loading: boolean;
  hasThread: boolean;
}

export function QueryInput({ onSubmit, onCancel, loading, hasThread }: QueryInputProps) {
  const [query, setQuery] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || loading) return;
    onSubmit(trimmed);
    setQuery("");
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 w-full">
      <div className="relative flex-1">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={
            hasThread ? "Ask a follow-up..." : "Ask about SEC filings..."
          }
          className="w-full h-10 rounded-lg border border-border/40 bg-card/60 px-3.5 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary/40 disabled:opacity-50 transition-colors"
          disabled={loading}
        />
      </div>
      {loading ? (
        <button
          type="button"
          onClick={onCancel}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors"
          title="Stop analysis"
        >
          <Square className="h-3.5 w-3.5 fill-current" />
        </button>
      ) : (
        <button
          type="submit"
          disabled={!query.trim()}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground disabled:opacity-40 hover:bg-primary/90 transition-colors"
        >
          <ArrowUp className="h-4 w-4" />
        </button>
      )}
    </form>
  );
}
