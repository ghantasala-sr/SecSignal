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
  // --- Advanced viz imports (removable: advanced-viz) ---
  ComposedChart,
  Area,
  AreaChart as RechartsAreaChart,
  Pie,
  PieChart as RechartsPieChart,
  Radar,
  RadarChart as RechartsRadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ReferenceLine,
  // --- End advanced viz imports ---
} from "recharts";

const CHART_COLORS = [
  "#5eadad",
  "#3B82F6",
  "#10B981",
  "#8B5CF6",
  "#EF4444",
  "#06B6D4",
  "#F59E0B",
  "#EC4899",
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
            {/* --- Advanced viz routing (removable: advanced-viz) --- */}
            {chart.chart_type === "composed" ? (
              <ComposedBarLineChart chart={chart} />
            ) : chart.chart_type === "area" ? (
              <AreaChartComponent chart={chart} />
            ) : chart.chart_type === "pie" ? (
              <PieChartComponent chart={chart} />
            ) : chart.chart_type === "radar" ? (
              <RadarChartComponent chart={chart} />
            ) : chart.chart_type === "waterfall" ? (
              <WaterfallChart chart={chart} />
            ) : /* --- End advanced viz routing --- */
            chart.chart_type === "grouped_bar" ? (
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

// ---------------------------------------------------------------------------
// Original chart components
// ---------------------------------------------------------------------------

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
      {/* --- Reference lines (removable: advanced-viz) --- */}
      {chart.reference_lines?.map((rl, i) => (
        <ReferenceLine
          key={i}
          y={rl.axis === "x" ? undefined : rl.value}
          x={rl.axis === "x" ? String(rl.value) : undefined}
          stroke={rl.color}
          strokeDasharray="4 4"
          label={{ value: rl.label, fill: rl.color, fontSize: 10 }}
        />
      ))}
      {/* --- End reference lines --- */}
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
      {/* --- Reference lines (removable: advanced-viz) --- */}
      {chart.reference_lines?.map((rl, i) => (
        <ReferenceLine
          key={i}
          y={rl.value}
          stroke={rl.color}
          strokeDasharray="4 4"
          label={{ value: rl.label, fill: rl.color, fontSize: 10 }}
        />
      ))}
      {/* --- End reference lines --- */}
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
      {/* --- Reference lines (removable: advanced-viz) --- */}
      {chart.reference_lines?.map((rl, i) => (
        <ReferenceLine
          key={`ref-${i}`}
          y={rl.value}
          stroke={rl.color}
          strokeDasharray="4 4"
          label={{ value: rl.label, fill: rl.color, fontSize: 10 }}
        />
      ))}
      {/* --- End reference lines --- */}
    </BarChart>
  );
}

// ---------------------------------------------------------------------------
// --- Advanced chart components (removable: advanced-viz) ---
// ---------------------------------------------------------------------------

/**
 * ComposedBarLineChart — Combines bars and lines in one chart.
 * Use case: Revenue (bars) vs margin % (line overlay) for comparison.
 * Data shape: series[0] renders as Bar, series[1+] render as Lines.
 * Falls back to SingleBarChart if no series provided.
 */
function ComposedBarLineChart({ chart }: { chart: GeneratedChart }) {
  const series = chart.series ?? [];
  if (series.length < 2) {
    return <SingleBarChart chart={chart} />;
  }

  const barSeries = series[0];
  const lineSeries = series.slice(1);

  return (
    <ComposedChart data={chart.data}>
      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
      <XAxis
        dataKey="label"
        tick={AXIS_TICK}
        tickLine={false}
        axisLine={false}
      />
      <YAxis
        yAxisId="left"
        tick={AXIS_TICK}
        tickLine={false}
        axisLine={false}
        width={55}
      />
      <YAxis
        yAxisId="right"
        orientation="right"
        tick={AXIS_TICK}
        tickLine={false}
        axisLine={false}
        width={45}
      />
      <Tooltip contentStyle={TOOLTIP_STYLE} />
      <Legend
        wrapperStyle={{ fontSize: "11px", paddingTop: "4px" }}
        iconType="square"
        iconSize={8}
      />
      <Bar
        yAxisId="left"
        dataKey={barSeries.key}
        name={barSeries.name}
        fill={barSeries.color}
        radius={[4, 4, 0, 0]}
        barSize={20}
      />
      {lineSeries.map((s, i) => (
        <Line
          key={s.key}
          yAxisId="right"
          type="monotone"
          dataKey={s.key}
          name={s.name}
          stroke={s.color}
          strokeWidth={2}
          dot={{ r: 3, fill: s.color }}
        />
      ))}
      {chart.reference_lines?.map((rl, i) => (
        <ReferenceLine
          key={`ref-${i}`}
          yAxisId="left"
          y={rl.value}
          stroke={rl.color}
          strokeDasharray="4 4"
          label={{ value: rl.label, fill: rl.color, fontSize: 10 }}
        />
      ))}
    </ComposedChart>
  );
}

/**
 * AreaChartComponent — Filled area chart for trends/cumulative data.
 * Use case: Revenue growth over time, cash flow trends.
 * Supports multiple series as stacked or overlaid areas.
 */
function AreaChartComponent({ chart }: { chart: GeneratedChart }) {
  const series = chart.series ?? [];

  if (series.length === 0) {
    // Single-value area
    return (
      <RechartsAreaChart data={chart.data}>
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
        <defs>
          <linearGradient id="areaGrad0" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={CHART_COLORS[0]} stopOpacity={0.4} />
            <stop offset="95%" stopColor={CHART_COLORS[0]} stopOpacity={0.05} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="value"
          stroke={CHART_COLORS[0]}
          strokeWidth={2}
          fill="url(#areaGrad0)"
        />
        {chart.reference_lines?.map((rl, i) => (
          <ReferenceLine
            key={i}
            y={rl.value}
            stroke={rl.color}
            strokeDasharray="4 4"
            label={{ value: rl.label, fill: rl.color, fontSize: 10 }}
          />
        ))}
      </RechartsAreaChart>
    );
  }

  // Multi-series area
  return (
    <RechartsAreaChart data={chart.data}>
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
      <Legend
        wrapperStyle={{ fontSize: "11px", paddingTop: "4px" }}
        iconType="square"
        iconSize={8}
      />
      <defs>
        {series.map((s, i) => (
          <linearGradient key={s.key} id={`areaGrad-${s.key}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={s.color} stopOpacity={0.35} />
            <stop offset="95%" stopColor={s.color} stopOpacity={0.05} />
          </linearGradient>
        ))}
      </defs>
      {series.map((s) => (
        <Area
          key={s.key}
          type="monotone"
          dataKey={s.key}
          name={s.name}
          stroke={s.color}
          strokeWidth={2}
          fill={`url(#areaGrad-${s.key})`}
        />
      ))}
      {chart.reference_lines?.map((rl, i) => (
        <ReferenceLine
          key={i}
          y={rl.value}
          stroke={rl.color}
          strokeDasharray="4 4"
          label={{ value: rl.label, fill: rl.color, fontSize: 10 }}
        />
      ))}
    </RechartsAreaChart>
  );
}

/**
 * PieChartComponent — Proportional distribution chart.
 * Use case: Expense breakdown by category, revenue share by segment.
 * Data shape: each data point has { label, value }.
 */
function PieChartComponent({ chart }: { chart: GeneratedChart }) {
  return (
    <RechartsPieChart>
      <Tooltip contentStyle={TOOLTIP_STYLE} />
      <Legend
        wrapperStyle={{ fontSize: "10px" }}
        iconType="circle"
        iconSize={8}
      />
      <Pie
        data={chart.data}
        dataKey="value"
        nameKey="label"
        cx="50%"
        cy="45%"
        outerRadius="70%"
        innerRadius="35%"
        paddingAngle={2}
        label={({ name, percent }: { name?: string; percent?: number }) =>
          `${name ?? ""} ${(((percent ?? 0)) * 100).toFixed(0)}%`
        }
        labelLine={false}
        fontSize={9}
      >
        {chart.data.map((_, idx) => (
          <Cell
            key={idx}
            fill={CHART_COLORS[idx % CHART_COLORS.length]}
            stroke="rgba(0,0,0,0.3)"
            strokeWidth={1}
          />
        ))}
      </Pie>
    </RechartsPieChart>
  );
}

/**
 * RadarChartComponent — Multi-dimensional comparison.
 * Use case: Company health profile (profitability, growth, risk, liquidity, etc.).
 * Data shape: each point has { label, value } or multi-series via series[].
 */
function RadarChartComponent({ chart }: { chart: GeneratedChart }) {
  const series = chart.series ?? [];

  return (
    <RechartsRadarChart cx="50%" cy="50%" outerRadius="65%" data={chart.data}>
      <PolarGrid stroke="rgba(255,255,255,0.1)" />
      <PolarAngleAxis
        dataKey="label"
        tick={{ fontSize: 9, fill: "rgba(255,255,255,0.6)" }}
      />
      <PolarRadiusAxis
        tick={{ fontSize: 8, fill: "rgba(255,255,255,0.4)" }}
        axisLine={false}
      />
      <Tooltip contentStyle={TOOLTIP_STYLE} />
      {series.length > 0 ? (
        <>
          <Legend
            wrapperStyle={{ fontSize: "10px" }}
            iconType="circle"
            iconSize={8}
          />
          {series.map((s, i) => (
            <Radar
              key={s.key}
              name={s.name}
              dataKey={s.key}
              stroke={s.color}
              fill={s.color}
              fillOpacity={0.15}
              strokeWidth={2}
            />
          ))}
        </>
      ) : (
        <Radar
          name={chart.ticker}
          dataKey="value"
          stroke={CHART_COLORS[0]}
          fill={CHART_COLORS[0]}
          fillOpacity={0.2}
          strokeWidth={2}
        />
      )}
    </RechartsRadarChart>
  );
}

/**
 * WaterfallChart — Shows incremental changes (positive/negative contributions).
 * Use case: Income statement waterfall (Revenue → COGS → Gross Profit → … → Net Income).
 * Data shape: each point has { label, value } where value is the delta.
 * Internally computes running totals and renders green (positive) / red (negative) bars.
 */
function WaterfallChart({ chart }: { chart: GeneratedChart }) {
  // Compute running totals for waterfall positioning
  const waterfallData = chart.data.map((d, i) => {
    const val = d.value ?? 0;
    const prevTotal = chart.data
      .slice(0, i)
      .reduce((sum, p) => sum + (p.value ?? 0), 0);
    return {
      label: d.label,
      value: val,
      base: val >= 0 ? prevTotal : prevTotal + val,
      height: Math.abs(val),
      total: prevTotal + val,
      isPositive: val >= 0,
    };
  });

  return (
    <BarChart data={waterfallData}>
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
        width={55}
      />
      <Tooltip
        contentStyle={TOOLTIP_STYLE}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        formatter={((value: any, name: any) => {
          if (name === "base") return [null, null];
          const v = typeof value === "number" ? value : Number(value);
          return [v.toLocaleString(), "Change"];
        }) as any}
      />
      {/* Invisible base bar for stacking offset */}
      <Bar dataKey="base" stackId="waterfall" fill="transparent" />
      {/* Visible delta bar stacked on top */}
      <Bar dataKey="height" stackId="waterfall" radius={[3, 3, 0, 0]}>
        {waterfallData.map((d, idx) => (
          <Cell
            key={idx}
            fill={d.isPositive ? "#10B981" : "#EF4444"}
          />
        ))}
      </Bar>
      {chart.reference_lines?.map((rl, i) => (
        <ReferenceLine
          key={i}
          y={rl.value}
          stroke={rl.color}
          strokeDasharray="4 4"
          label={{ value: rl.label, fill: rl.color, fontSize: 10 }}
        />
      ))}
    </BarChart>
  );
}

// --- End advanced chart components ---
