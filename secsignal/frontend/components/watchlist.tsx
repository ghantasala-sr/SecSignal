"use client";

import { useEffect, useState } from "react";
import { Star, X, Plus, TrendingUp, DollarSign, MessageSquare } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const STORAGE_KEY = "secsignal_watchlist";

const KNOWN_TICKERS: Record<string, string> = {
  AAPL: "Apple Inc.",
  AMZN: "Amazon.com Inc.",
  GOOGL: "Alphabet Inc.",
  MSFT: "Microsoft Corp.",
  NVDA: "NVIDIA Corp.",
  TSLA: "Tesla Inc.",
};

interface WatchlistProps {
  onQuery: (query: string) => void;
}

export function Watchlist({ onQuery }: WatchlistProps) {
  const [tickers, setTickers] = useState<string[]>([]);
  const [adding, setAdding] = useState(false);
  const [input, setInput] = useState("");

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) setTickers(JSON.parse(stored));
    } catch { /* ignore */ }
  }, []);

  function persist(next: string[]) {
    setTickers(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }

  function addTicker(t: string) {
    const upper = t.trim().toUpperCase();
    if (!upper || tickers.includes(upper)) return;
    if (!(upper in KNOWN_TICKERS)) return;
    persist([...tickers, upper]);
    setInput("");
    setAdding(false);
  }

  function removeTicker(t: string) {
    persist(tickers.filter((x) => x !== t));
  }

  const suggestions = input.length > 0
    ? Object.entries(KNOWN_TICKERS).filter(
        ([sym]) => sym.startsWith(input.toUpperCase()) && !tickers.includes(sym)
      )
    : [];

  return (
    <div className="rounded-lg border border-border/30 bg-card/50 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs font-medium text-foreground/70">
          <Star className="h-3.5 w-3.5 text-yellow-500/70" />
          <span>Watchlist</span>
          {tickers.length > 0 && (
            <Badge variant="secondary" className="text-[10px] ml-1">
              {tickers.length}
            </Badge>
          )}
        </div>
        {!adding && (
          <button
            onClick={() => setAdding(true)}
            className="text-xs text-primary/60 hover:text-primary transition-colors flex items-center gap-1"
          >
            <Plus className="h-3 w-3" />
            Add
          </button>
        )}
      </div>

      {/* Add ticker input */}
      {adding && (
        <div className="relative">
          <input
            autoFocus
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") addTicker(input);
              if (e.key === "Escape") { setAdding(false); setInput(""); }
            }}
            placeholder="Ticker symbol..."
            className="w-full text-xs bg-background/50 border border-border/40 rounded px-2.5 py-1.5 outline-none focus:border-primary/40 placeholder:text-muted-foreground/40"
          />
          {suggestions.length > 0 && (
            <div className="absolute z-10 top-full mt-1 w-full bg-background border border-border/40 rounded shadow-lg max-h-32 overflow-y-auto">
              {suggestions.map(([sym, name]) => (
                <button
                  key={sym}
                  onClick={() => addTicker(sym)}
                  className="w-full text-left px-2.5 py-1.5 text-xs hover:bg-primary/10 transition-colors"
                >
                  <span className="font-mono font-medium">{sym}</span>
                  <span className="text-muted-foreground ml-2">{name}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Ticker list */}
      {tickers.length === 0 && !adding && (
        <p className="text-[11px] text-muted-foreground/50">
          Add tickers to quickly query them.
        </p>
      )}

      <div className="space-y-1.5">
        {tickers.map((t) => (
          <div
            key={t}
            className="group flex items-center gap-2 rounded px-2 py-1.5 hover:bg-foreground/5 transition-colors"
          >
            <span className="font-mono text-xs font-medium text-foreground/80 w-12">{t}</span>
            <span className="text-[11px] text-muted-foreground/60 flex-1 truncate">
              {KNOWN_TICKERS[t] ?? ""}
            </span>
            <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                onClick={() => onQuery(`What are the latest trends for ${t}?`)}
                title="Trend analysis"
                className="p-1 rounded hover:bg-primary/10 text-muted-foreground/50 hover:text-primary transition-colors"
              >
                <TrendingUp className="h-3 w-3" />
              </button>
              <button
                onClick={() => onQuery(`What is ${t}'s valuation profile?`)}
                title="Valuation"
                className="p-1 rounded hover:bg-primary/10 text-muted-foreground/50 hover:text-primary transition-colors"
              >
                <DollarSign className="h-3 w-3" />
              </button>
              <button
                onClick={() => onQuery(`How has ${t}'s management tone changed in recent filings?`)}
                title="Sentiment"
                className="p-1 rounded hover:bg-primary/10 text-muted-foreground/50 hover:text-primary transition-colors"
              >
                <MessageSquare className="h-3 w-3" />
              </button>
              <button
                onClick={() => removeTicker(t)}
                title="Remove from watchlist"
                className="p-1 rounded hover:bg-red-500/10 text-muted-foreground/50 hover:text-red-400 transition-colors"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Quick compare */}
      {tickers.length >= 2 && (
        <button
          onClick={() => onQuery(`Compare ${tickers.join(", ")} across key financial metrics`)}
          className="w-full text-[11px] text-center py-1.5 rounded border border-primary/20 text-primary/60 hover:text-primary hover:border-primary/40 hover:bg-primary/5 transition-all"
        >
          Compare all {tickers.length} tickers
        </button>
      )}
    </div>
  );
}
