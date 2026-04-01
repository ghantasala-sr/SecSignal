"use client";

import { useEffect, useRef } from "react";
import { useQueryStream } from "@/lib/use-query-stream";
import { QueryInput } from "@/components/query-input";
import { ThreadMessage } from "@/components/thread-message";
import { TrendingUp, GitCompareArrows, AlertTriangle } from "lucide-react";

export default function Home() {
  const { messages, loading, submit, cancel, clearThread } = useQueryStream();
  const scrollRef = useRef<HTMLDivElement>(null);

  const hasMessages = messages.length > 0;

  function handleQuery(query: string) {
    submit({ query });
  }

  // Auto-scroll to bottom when new messages arrive or content updates
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <div className="flex flex-col flex-1">
      {/* Scrollable content area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {!hasMessages ? (
          /* Landing / Hero */
          <div className="flex flex-col items-center justify-center min-h-full px-6 py-16">
            <div className="max-w-2xl text-center space-y-5">
              <h2 className="font-heading text-3xl md:text-4xl tracking-tight leading-tight">
                Intelligence from
                <br />
                <span className="text-primary">SEC Filings</span>
              </h2>
              <p className="text-muted-foreground text-base max-w-lg mx-auto">
                Analyze trends, compare companies, and detect anomalies across
                10-K and 10-Q filings.
              </p>

              {/* Capability suggestions */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-4 text-left">
                <CapabilityCard
                  icon={<TrendingUp className="w-4 h-4" />}
                  title="Trends"
                  description="Track risk factor changes over time"
                  example="How have Apple's risk factors changed?"
                  onExample={handleQuery}
                />
                <CapabilityCard
                  icon={<GitCompareArrows className="w-4 h-4" />}
                  title="Compare"
                  description="Compare metrics across companies"
                  example="Compare risk profiles of NVDA, TSLA, and MSFT"
                  onExample={handleQuery}
                />
                <CapabilityCard
                  icon={<AlertTriangle className="w-4 h-4" />}
                  title="Anomalies"
                  description="Surface unusual disclosure changes"
                  example="Find anomalies in recent tech company filings"
                  onExample={handleQuery}
                />
              </div>

              <div className="pt-2">
                <QueryInput
                  onSubmit={handleQuery}
                  loading={loading}
                  hasThread={false}
                />
              </div>
            </div>
          </div>
        ) : (
          /* Thread messages */
          <div className="max-w-5xl mx-auto px-6 py-6 space-y-8">
            <div className="flex justify-end">
              <button
                onClick={clearThread}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                New thread
              </button>
            </div>
            {messages.map((msg, i) => (
              <ThreadMessage
                key={msg.id}
                message={msg}
                isLatest={i === messages.length - 1}
              />
            ))}
          </div>
        )}
      </div>

      {/* Pinned input (only in thread mode) */}
      {hasMessages && (
        <div className="border-t border-border/40 px-6 py-3 shrink-0 bg-background">
          <div className="max-w-3xl mx-auto">
            <QueryInput
              onSubmit={handleQuery}
              loading={loading}
              hasThread={true}
            />
          </div>
        </div>
      )}

      {/* Footer — only on landing */}
      {!hasMessages && (
        <footer className="border-t border-border/30 px-6 py-3 shrink-0">
          <div className="max-w-5xl mx-auto text-center text-[11px] text-muted-foreground/50">
            Powered by Snowflake Cortex &middot; Agentic RAG
          </div>
        </footer>
      )}
    </div>
  );
}

function CapabilityCard({
  icon,
  title,
  description,
  example,
  onExample,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  example: string;
  onExample: (q: string) => void;
}) {
  return (
    <button
      onClick={() => onExample(example)}
      className="group rounded-lg border border-border/30 bg-card/50 p-3.5 text-left transition-colors hover:border-border/60"
    >
      <div className="flex items-center gap-2 mb-1.5 text-primary/80">
        {icon}
        <span className="font-medium text-xs text-foreground/80">{title}</span>
      </div>
      <p className="text-[11px] text-muted-foreground mb-2">{description}</p>
      <p className="text-[11px] text-muted-foreground/70 group-hover:text-muted-foreground transition-colors">
        &ldquo;{example}&rdquo;
      </p>
    </button>
  );
}
