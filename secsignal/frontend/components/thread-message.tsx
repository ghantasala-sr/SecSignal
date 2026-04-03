"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, RefreshCw, User } from "lucide-react";
import type { ThreadMessage as ThreadMessageType } from "@/lib/use-query-stream";
import { AgentTrajectory } from "@/components/agent-trajectory";
import { AnalysisResult } from "@/components/analysis-result";
import { AnalysisSkeleton } from "@/components/analysis-skeleton";

interface ThreadMessageProps {
  message: ThreadMessageType;
  isLatest: boolean;
  onRetry?: (messageId: string) => void;
  onFollowUp?: (query: string) => void;
}

/** Sum up duration_ms across all completed trajectory steps. */
function totalElapsedMs(message: ThreadMessageType): number | null {
  const durations = message.trajectory
    .map((s) => s.duration_ms)
    .filter((d): d is number => d != null);
  if (durations.length === 0) return null;
  return durations.reduce((a, b) => a + b, 0);
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function ThreadMessage({ message, isLatest, onRetry, onFollowUp }: ThreadMessageProps) {
  const [trajectoryOpen, setTrajectoryOpen] = useState(isLatest);

  return (
    <div className="space-y-3">
      {/* User query */}
      <div className="flex items-start gap-3 max-w-3xl">
        <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-foreground/10">
          <User className="h-3.5 w-3.5 text-foreground/60" />
        </div>
        <p className="text-sm text-foreground/90 pt-0.5 leading-relaxed">
          {message.query}
        </p>
      </div>

      {/* Agent trajectory (collapsible) */}
      {message.trajectory.length > 0 && (
        <div className="ml-9">
          <button
            onClick={() => setTrajectoryOpen((o) => !o)}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground/70 transition-colors mb-2"
          >
            {trajectoryOpen ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
            <span>
              {message.trajectory.length} agent step
              {message.trajectory.length !== 1 ? "s" : ""}
              {(() => {
                const total = totalElapsedMs(message);
                return total != null ? ` \u00b7 ${formatMs(total)}` : "";
              })()}
            </span>
          </button>
          {trajectoryOpen && (
            <AgentTrajectory
              steps={message.trajectory}
              loading={message.loading}
            />
          )}
        </div>
      )}

      {/* Loading spinner when no trajectory yet */}
      {message.loading && message.trajectory.length === 0 && (
        <div className="ml-9 flex items-center gap-2 text-sm text-muted-foreground">
          <div className="h-3 w-3 rounded-full border-2 border-primary border-t-transparent animate-spin" />
          <span>Starting analysis...</span>
        </div>
      )}

      {/* Skeleton loader while waiting for result */}
      {message.loading && message.trajectory.length > 0 && !message.result && (
        <div className="ml-0">
          <AnalysisSkeleton />
        </div>
      )}

      {/* Error */}
      {message.error && (
        <div className="ml-9 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2">
          <p className="text-sm text-destructive">{message.error}</p>
          {onRetry && (
            <button
              onClick={() => onRetry(message.id)}
              className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-destructive hover:text-destructive/80 transition-colors"
            >
              <RefreshCw className="h-3 w-3" />
              Retry
            </button>
          )}
        </div>
      )}

      {/* Result */}
      {message.result && (
        <div className="ml-0">
          <AnalysisResult data={message.result} onFollowUp={onFollowUp} />
        </div>
      )}
    </div>
  );
}
