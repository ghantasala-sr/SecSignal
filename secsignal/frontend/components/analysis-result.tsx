"use client";

import { useRef, useState } from "react";
import type { QueryResponse } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ChartPanel } from "@/components/chart-panel";
import { AnomalyCard } from "@/components/anomaly-card";
import { SourceList } from "@/components/source-list";
import { WebSourceList } from "@/components/web-source-list";
import { ChevronDown, ChevronRight, Download, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface AnalysisResultProps {
  data: QueryResponse;
  onFollowUp?: (query: string) => void;
}

const queryTypeLabels: Record<string, string> = {
  trend: "Trend Analysis",
  comparison: "Company Comparison",
  anomaly: "Anomaly Detection",
};

function confidenceColor(score: number): string {
  if (score >= 0.8) return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
  if (score >= 0.5) return "bg-yellow-500/15 text-yellow-400 border-yellow-500/30";
  return "bg-red-500/15 text-red-400 border-red-500/30";
}

function confidenceLabel(score: number): string {
  if (score >= 0.8) return "High confidence";
  if (score >= 0.5) return "Medium confidence";
  return "Low confidence";
}

export function AnalysisResult({ data, onFollowUp }: AnalysisResultProps) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const printRef = useRef<HTMLDivElement>(null);
  const hasSources = data.sources.length > 0 || data.web_sources.length > 0;
  const totalSources = data.sources.length + data.web_sources.length;

  function handleExport() {
    const el = printRef.current;
    if (!el) return;
    const win = window.open("", "_blank");
    if (!win) return;
    win.document.write(`<!DOCTYPE html><html><head><title>SecSignal — ${data.tickers.join(", ")}</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 800px; margin: 2rem auto; color: #1a1a1a; padding: 0 1rem; }
  h1,h2,h3,h4 { margin-top: 1.2em; }
  table { border-collapse: collapse; width: 100%; margin: 1em 0; }
  th,td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; font-size: 13px; }
  th { background: #f5f5f5; }
  .meta { color: #666; font-size: 12px; margin-bottom: 1.5rem; }
  .badge { display: inline-block; background: #f0f0f0; border-radius: 4px; padding: 2px 8px; font-size: 11px; margin-right: 4px; }
  img { max-width: 100%; }
  svg { max-width: 100%; }
  canvas { max-width: 100%; }
</style></head><body>`);
    win.document.write(`<div class="meta">SecSignal Analysis &mdash; ${new Date().toLocaleDateString()} &mdash; ${data.query_type} &mdash; ${data.tickers.map(t => `<span class="badge">${t}</span>`).join(" ")}</div>`);
    win.document.write(el.innerHTML);
    win.document.write(`</body></html>`);
    win.document.close();
    setTimeout(() => { win.print(); }, 400);
  }

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
        {data.confidence_score > 0 && (
          <Badge
            variant="outline"
            className={`text-[10px] ml-auto ${confidenceColor(data.confidence_score)}`}
            title={`Confidence: ${Math.round(data.confidence_score * 100)}%`}
          >
            {confidenceLabel(data.confidence_score)} ({Math.round(data.confidence_score * 100)}%)
          </Badge>
        )}
        <button
          onClick={handleExport}
          title="Export as PDF"
          className="ml-2 p-1 rounded hover:bg-foreground/10 text-foreground/50 hover:text-foreground/80 transition-colors"
        >
          <Download className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Printable content */}
      <div ref={printRef}>
      {/* Answer */}
      <div className="prose prose-invert prose-sm max-w-none text-foreground/85 prose-headings:font-heading prose-headings:text-foreground/90 prose-strong:text-foreground/90 prose-li:marker:text-primary/40 prose-p:leading-relaxed">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.answer}</ReactMarkdown>
      </div>

      {/* Follow-up suggestions */}
      {data.follow_up_questions?.length > 0 && onFollowUp && (
        <>
          <Separator className="opacity-20" />
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs text-foreground/50">
              <Sparkles className="h-3 w-3" />
              <span>Suggested follow-ups</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {data.follow_up_questions.map((q, i) => (
                <button
                  key={i}
                  onClick={() => onFollowUp(q)}
                  className="text-left text-xs px-3 py-1.5 rounded-full border border-primary/20 text-primary/70 hover:text-primary hover:border-primary/40 hover:bg-primary/5 transition-all duration-150"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        </>
      )}

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
      </div>{/* end printRef */}

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
