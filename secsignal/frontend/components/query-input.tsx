"use client";

import { useCallback, useRef, useState } from "react";
import { ArrowUp, Square } from "lucide-react";

const KNOWN_TICKERS: { ticker: string; name: string }[] = [
  { ticker: "AAPL", name: "Apple Inc." },
  { ticker: "AMZN", name: "Amazon.com Inc." },
  { ticker: "GOOGL", name: "Alphabet Inc." },
  { ticker: "MSFT", name: "Microsoft Corp." },
  { ticker: "NVDA", name: "NVIDIA Corp." },
  { ticker: "TSLA", name: "Tesla Inc." },
];

interface QueryInputProps {
  onSubmit: (query: string) => void;
  onCancel?: () => void;
  loading: boolean;
  hasThread: boolean;
}

export function QueryInput({ onSubmit, onCancel, loading, hasThread }: QueryInputProps) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<typeof KNOWN_TICKERS>([]);
  const [selectedIdx, setSelectedIdx] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || loading) return;
    setSuggestions([]);
    onSubmit(trimmed);
    setQuery("");
  }

  const updateSuggestions = useCallback((value: string) => {
    // Find the word being typed at cursor position
    const words = value.split(/\s+/);
    const lastWord = words[words.length - 1]?.toUpperCase() ?? "";
    if (lastWord.length >= 1) {
      const matches = KNOWN_TICKERS.filter(
        (t) => t.ticker.startsWith(lastWord) && t.ticker !== lastWord,
      );
      setSuggestions(matches);
      setSelectedIdx(-1);
    } else {
      setSuggestions([]);
    }
  }, []);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const value = e.target.value;
    setQuery(value);
    updateSuggestions(value);
  }

  function insertTicker(ticker: string) {
    const words = query.split(/\s+/);
    words[words.length - 1] = ticker;
    const newQuery = words.join(" ") + " ";
    setQuery(newQuery);
    setSuggestions([]);
    setSelectedIdx(-1);
    inputRef.current?.focus();
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (suggestions.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIdx((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Tab" || e.key === "Enter") {
      if (selectedIdx >= 0 && selectedIdx < suggestions.length) {
        e.preventDefault();
        insertTicker(suggestions[selectedIdx].ticker);
      } else if (e.key === "Tab" && suggestions.length > 0) {
        e.preventDefault();
        insertTicker(suggestions[0].ticker);
      }
    } else if (e.key === "Escape") {
      setSuggestions([]);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 w-full">
      <div className="relative flex-1">
        <input
          ref={inputRef}
          value={query}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onBlur={() => setTimeout(() => setSuggestions([]), 150)}
          placeholder={
            hasThread ? "Ask a follow-up..." : "Ask about SEC filings..."
          }
          className="w-full h-10 rounded-lg border border-border/40 bg-card/60 px-3.5 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary/40 disabled:opacity-50 transition-colors"
          disabled={loading}
        />

        {/* Ticker autocomplete dropdown */}
        {suggestions.length > 0 && (
          <div className="absolute left-0 right-0 bottom-full mb-1 z-50 rounded-lg border border-border/40 bg-card shadow-lg overflow-hidden">
            {suggestions.map((s, i) => (
              <button
                key={s.ticker}
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  insertTicker(s.ticker);
                }}
                className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 transition-colors ${
                  i === selectedIdx
                    ? "bg-primary/10 text-foreground"
                    : "text-foreground/80 hover:bg-muted/50"
                }`}
              >
                <span className="font-mono font-medium text-primary">{s.ticker}</span>
                <span className="text-xs text-muted-foreground">{s.name}</span>
              </button>
            ))}
          </div>
        )}
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
