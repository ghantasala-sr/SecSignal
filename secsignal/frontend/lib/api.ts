// SecSignal API client — talks to FastAPI backend

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChartDataPoint {
  label: string;
  value?: number;
  [key: string]: string | number | undefined;
}

export interface ChartSeries {
  key: string;
  name: string;
  color: string;
}

export interface GeneratedChart {
  chart_type: "bar" | "line" | "grouped_bar";
  title: string;
  category: string;
  unit: string;
  ticker: string;
  data: ChartDataPoint[];
  series?: ChartSeries[];
}

export interface RetrievedChart {
  image_id: string;
  ticker: string;
  filing_type: string;
  description: string;
  similarity: number;
}

export interface AnomalyScore {
  ticker: string;
  metric: string;
  filing_date: string;
  value: number;
  z_score: number;
  direction: string;
}

export interface Source {
  ticker: string;
  filing_type: string;
  section: string;
  similarity?: number;
  snippet: string;
}

export interface WebSource {
  title: string;
  url: string;
  snippet: string;
}

export interface QueryResponse {
  query: string;
  query_type: string;
  tickers: string[];
  answer: string;
  sources: Source[];
  charts: RetrievedChart[];
  anomalies: AnomalyScore[];
  generated_charts: GeneratedChart[];
  web_sources: WebSource[];
}

export interface QueryRequest {
  query: string;
  tickers?: string[];
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function submitQuery(req: QueryRequest): Promise<QueryResponse> {
  const res = await fetch(`${API_BASE}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Query failed (${res.status}): ${detail}`);
  }

  return res.json();
}

export function chartImageUrl(imageId: string): string {
  return `${API_BASE}/api/charts/${imageId}`;
}
