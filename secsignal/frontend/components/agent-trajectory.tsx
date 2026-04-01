"use client";

import type { TrajectoryStep } from "@/lib/use-query-stream";

// Map node names to icons (simple unicode for zero-dependency approach)
const NODE_ICONS: Record<string, string> = {
  classify_query: "\u{1F50D}", // magnifying glass
  trend_agent: "\u{1F4C8}", // chart increasing
  comparison_agent: "\u{1F4CA}", // bar chart
  anomaly_agent: "\u{26A0}\uFE0F", // warning
  web_search_agent: "\u{1F310}", // globe
  synthesizer: "\u{2728}", // sparkles
};

interface AgentTrajectoryProps {
  steps: TrajectoryStep[];
  loading: boolean;
}

export function AgentTrajectory({ steps, loading }: AgentTrajectoryProps) {
  if (steps.length === 0 && !loading) return null;

  return (
    <div className="w-full max-w-xl mb-4">
      <div className="relative">
        {/* Vertical line */}
        <div className="absolute left-[7px] top-1 bottom-1 w-px bg-border/60" />

        <div className="space-y-2">
          {steps.map((step) => (
            <TrajectoryNode key={step.step} step={step} />
          ))}

          {/* Active spinner when still loading */}
          {loading && (
            <div className="relative flex items-center gap-2.5 pl-6">
              <div className="absolute left-[4px] w-[7px] h-[7px] rounded-full border border-primary/60 bg-background animate-pulse" />
              <span className="text-xs text-muted-foreground/70 animate-pulse">
                Processing...
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TrajectoryNode({ step }: { step: TrajectoryStep }) {
  const icon = NODE_ICONS[step.node] ?? "\u{2699}\uFE0F";
  const detailEntries = Object.entries(step.detail).filter(
    ([, v]) => v !== undefined && v !== null && v !== "" && !(Array.isArray(v) && v.length === 0),
  );

  return (
    <div className="relative flex items-start gap-2.5 pl-6 animate-in fade-in duration-200">
      {/* Timeline dot */}
      <div className="absolute left-[3px] top-[5px] w-[9px] h-[9px] rounded-full bg-primary/70" />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs" aria-hidden>
            {icon}
          </span>
          <span className="text-xs font-medium text-foreground/80">
            {step.label}
          </span>
          <span className="text-[10px] text-muted-foreground/50 font-mono">
            {step.node}
          </span>
        </div>

        {/* Detail chips */}
        {detailEntries.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-0.5">
            {detailEntries.map(([key, value]) => (
              <span
                key={key}
                className="text-[10px] text-muted-foreground/60 bg-muted/30 px-1.5 py-0 rounded"
              >
                {formatDetailKey(key)}:{" "}
                <span className="text-foreground/50">
                  {formatDetailValue(value)}
                </span>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function formatDetailKey(key: string): string {
  return key.replace(/_/g, " ");
}

function formatDetailValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "number") return value.toLocaleString();
  return String(value);
}
