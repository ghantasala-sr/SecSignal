"use client";

import { useState } from "react";
import type { QueryResponse } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ChartPanel } from "@/components/chart-panel";
import { AnomalyCard } from "@/components/anomaly-card";
import { SourceList } from "@/components/source-list";
import { WebSourceList } from "@/components/web-source-list";
import { ChevronDown, ChevronRight } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface AnalysisResultProps {
  data: QueryResponse;
}

const queryTypeLabels: Record<string, string> = {
  trend: "Trend Analysis",
  comparison: "Company Comparison",
  anomaly: "Anomaly Detection",
};

export function AnalysisResult({ data }: AnalysisResultProps) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const hasSources = data.sources.length > 0 || data.web_sources.length > 0;
  const totalSources = data.sources.length + data.web_sources.length;

  return (
    <div className="max-w-4xl space-y-6 animate-in fade-in duration-300">
      {/* Header row */}
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="outline" className="text-primary/80 border-primary/20 text-[11px]">
          {queryTypeLabels[data.query_type] ?? data.query_type}
        </Badge>
        {data.tickers.map((t) => (
          <Badge key={t} variant="secondary" className="font-mono text-[10px]">
            {t}
          </Badge>
        ))}
      </div>

      {/* Answer */}
      <div className="prose prose-invert prose-sm max-w-none text-foreground/85 prose-headings:font-heading prose-headings:text-foreground/90 prose-strong:text-foreground/90 prose-li:marker:text-primary/40 prose-p:leading-relaxed">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.answer}</ReactMarkdown>
      </div>

      {/* Generated charts */}
      {/* --- Advanced viz grid (removable: advanced-viz) --- */}
      {data.generated_charts.length > 0 && (
        <>
          <Separator className="opacity-20" />
          <div className="space-y-3">
            <h4 className="text-sm font-medium text-foreground/70">Charts</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {data.generated_charts.map((chart, i) => (
                <div
                  key={i}
                  className={
                    chart.width_hint === "full"
                      ? "md:col-span-2"
                      : ""
                  }
                >
                  <ChartPanel chart={chart} />
                </div>
              ))}
            </div>
          </div>
        </>
      )}
      {/* --- End advanced viz grid --- */}

      {/* Anomalies */}
      {data.anomalies.length > 0 && (
        <>
          <Separator className="opacity-20" />
          <div className="space-y-3">
            <h4 className="text-sm font-medium text-foreground/70">
              Anomalies Detected
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {data.anomalies.map((a, i) => (
                <AnomalyCard key={i} anomaly={a} />
              ))}
            </div>
          </div>
        </>
      )}

      {/* Sources — collapsible dropdown */}
      {hasSources && (
        <>
          <Separator className="opacity-20" />
          <div className="space-y-2">
            <button
              onClick={() => setSourcesOpen((o) => !o)}
              className="flex items-center gap-2 text-sm font-medium text-foreground/70 hover:text-foreground/90 transition-colors w-full text-left"
            >
              {sourcesOpen ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
              <span>Sources</span>
              <Badge variant="secondary" className="text-[10px] ml-1">
                {totalSources}
              </Badge>
            </button>
            {sourcesOpen && (
              <div className="space-y-4 pl-6 animate-in slide-in-from-top-1 duration-200">
                {data.sources.length > 0 && (
                  <SourceList sources={data.sources} />
                )}
                {data.web_sources.length > 0 && (
                  <WebSourceList sources={data.web_sources} />
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
