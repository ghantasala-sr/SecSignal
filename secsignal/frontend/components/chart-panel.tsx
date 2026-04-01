"use client";

import type { GeneratedChart } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";

const CHART_COLORS = [
  "#5eadad",
  "#3B82F6",
  "#10B981",
  "#8B5CF6",
  "#EF4444",
  "#06B6D4",
];

const TOOLTIP_STYLE = {
  backgroundColor: "rgba(0,0,0,0.9)",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: "6px",
  fontSize: "12px",
};

const AXIS_TICK = { fontSize: 10, fill: "rgba(255,255,255,0.5)" };

interface ChartPanelProps {
  chart: GeneratedChart;
}

export function ChartPanel({ chart }: ChartPanelProps) {
  return (
    <Card className="bg-card/60 border-border/30">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">{chart.title}</CardTitle>
          <Badge variant="outline" className="text-xs font-mono">
            {chart.ticker}
          </Badge>
        </div>
        {chart.unit && (
          <p className="text-xs text-muted-foreground">{chart.unit}</p>
        )}
      </CardHeader>
      <CardContent>
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            {chart.chart_type === "grouped_bar" ? (
              <GroupedBarChart chart={chart} />
            ) : chart.chart_type === "line" ? (
              <SingleLineChart chart={chart} />
            ) : (
              <SingleBarChart chart={chart} />
            )}
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function SingleLineChart({ chart }: { chart: GeneratedChart }) {
  return (
    <LineChart data={chart.data}>
      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
      <XAxis
        dataKey="label"
        tick={AXIS_TICK}
        tickLine={false}
        axisLine={false}
      />
      <YAxis
        tick={AXIS_TICK}
        tickLine={false}
        axisLine={false}
        width={50}
      />
      <Tooltip contentStyle={TOOLTIP_STYLE} />
      <Line
        type="monotone"
        dataKey="value"
        stroke={CHART_COLORS[0]}
        strokeWidth={2}
        dot={{ r: 4, fill: CHART_COLORS[0] }}
      />
    </LineChart>
  );
}

function SingleBarChart({ chart }: { chart: GeneratedChart }) {
  return (
    <BarChart data={chart.data}>
      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
      <XAxis
        dataKey="label"
        tick={AXIS_TICK}
        tickLine={false}
        axisLine={false}
      />
      <YAxis
        tick={AXIS_TICK}
        tickLine={false}
        axisLine={false}
        width={50}
      />
      <Tooltip contentStyle={TOOLTIP_STYLE} />
      <Bar dataKey="value" radius={[4, 4, 0, 0]}>
        {chart.data.map((_, idx) => (
          <Cell
            key={idx}
            fill={CHART_COLORS[idx % CHART_COLORS.length]}
          />
        ))}
      </Bar>
    </BarChart>
  );
}

function GroupedBarChart({ chart }: { chart: GeneratedChart }) {
  const series = chart.series ?? [];
  if (series.length === 0) {
    return <SingleBarChart chart={chart} />;
  }

  return (
    <BarChart data={chart.data}>
      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
      <XAxis
        dataKey="label"
        tick={AXIS_TICK}
        tickLine={false}
        axisLine={false}
      />
      <YAxis
        tick={AXIS_TICK}
        tickLine={false}
        axisLine={false}
        width={60}
      />
      <Tooltip contentStyle={TOOLTIP_STYLE} />
      <Legend
        wrapperStyle={{ fontSize: "11px", paddingTop: "4px" }}
        iconType="square"
        iconSize={8}
      />
      {series.map((s) => (
        <Bar
          key={s.key}
          dataKey={s.key}
          name={s.name}
          fill={s.color}
          radius={[4, 4, 0, 0]}
        />
      ))}
    </BarChart>
  );
}
