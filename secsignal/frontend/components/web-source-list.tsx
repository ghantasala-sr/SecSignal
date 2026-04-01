import type { WebSource } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { ExternalLink } from "lucide-react";

interface WebSourceListProps {
  sources: WebSource[];
}

export function WebSourceList({ sources }: WebSourceListProps) {
  if (sources.length === 0) return null;

  return (
    <div className="space-y-3">
      <h3 className="font-heading text-xl tracking-tight">Web Sources</h3>
      <div className="space-y-2">
        {sources.map((source, i) => (
          <Card key={i} className="bg-card/50 border-border/30">
            <CardContent className="p-3 flex items-start gap-3">
              <ExternalLink className="w-4 h-4 text-primary/60 mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0 space-y-1">
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-medium text-primary/90 hover:text-primary hover:underline underline-offset-2 transition-colors line-clamp-1"
                >
                  {source.title || source.url}
                </a>
                {source.snippet && (
                  <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
                    {source.snippet}
                  </p>
                )}
                <span className="text-[10px] text-muted-foreground/40 break-all line-clamp-1">
                  {source.url}
                </span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
