import type { AnomalyScore } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, TrendingUp, TrendingDown } from "lucide-react";

interface AnomalyCardProps {
  anomaly: AnomalyScore;
}

export function AnomalyCard({ anomaly }: AnomalyCardProps) {
  const isUp = anomaly.direction === "above_mean";
  const severity = Math.abs(anomaly.z_score) >= 2 ? "high" : "moderate";

  return (
    <Card
      className={`border-l-2 ${
        severity === "high"
          ? "border-l-red-500/70 bg-red-500/[0.03]"
          : "border-l-amber-500/70 bg-amber-500/[0.03]"
      }`}
    >
      <CardContent className="p-3.5 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle
              className={`w-4 h-4 ${
                severity === "high" ? "text-red-500" : "text-amber-500"
              }`}
            />
            <span className="font-mono font-medium text-sm">
              {anomaly.ticker}
            </span>
          </div>
          <Badge
            variant="outline"
            className={
              severity === "high"
                ? "border-red-500/30 text-red-400"
                : "border-amber-500/30 text-amber-400"
            }
          >
            z = {anomaly.z_score > 0 ? "+" : ""}
            {anomaly.z_score.toFixed(2)}
          </Badge>
        </div>

        <div className="text-xs text-muted-foreground space-y-1">
          <div className="flex items-center justify-between">
            <span>{anomaly.metric}</span>
            <div className="flex items-center gap-1">
              {isUp ? (
                <TrendingUp className="w-3 h-3 text-red-400" />
              ) : (
                <TrendingDown className="w-3 h-3 text-emerald-400" />
              )}
              <span className="font-mono">
                {anomaly.value.toLocaleString()}
              </span>
            </div>
          </div>
          <div className="text-muted-foreground/60">{anomaly.filing_date}</div>
        </div>
      </CardContent>
    </Card>
  );
}
