import type { Source } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FileText } from "lucide-react";

interface SourceListProps {
  sources: Source[];
}

export function SourceList({ sources }: SourceListProps) {
  return (
    <div className="space-y-3">
      <h3 className="font-heading text-xl tracking-tight">Sources</h3>
      <div className="space-y-2">
        {sources.map((source, i) => (
          <Card key={i} className="bg-card/50 border-border/30">
            <CardContent className="p-3 flex items-start gap-3">
              <FileText className="w-4 h-4 text-muted-foreground mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0 space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="secondary" className="font-mono text-xs">
                    {source.ticker}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {source.filing_type}
                  </span>
                  <span className="text-xs text-muted-foreground/50">
                    {source.section}
                  </span>
                  <span className="text-xs text-muted-foreground/40 ml-auto">
                    {source.similarity != null
                      ? `${(source.similarity * 100).toFixed(0)}% match`
                      : ""}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
                  {source.snippet}
                </p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
