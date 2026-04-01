"use client";

import { useCallback, useRef, useState } from "react";
import type { QueryRequest, QueryResponse } from "./api";

const STREAM_BASE =
  process.env.NEXT_PUBLIC_STREAM_URL ?? "http://localhost:8000";

/** Threshold above which assistant answers get summarized instead of truncated. */
const SUMMARIZE_THRESHOLD = 1500;

/** Call /api/summarize to condense a long answer. Falls back to truncation. */
async function summarizeText(text: string): Promise<string> {
  try {
    const res = await fetch(`${STREAM_BASE}/api/summarize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) return text.slice(0, 3500);
    const data = await res.json();
    return data.summary ?? text.slice(0, 3500);
  } catch {
    return text.slice(0, 3500);
  }
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TrajectoryStep {
  step: number;
  node: string;
  label: string;
  detail: Record<string, unknown>;
  status: "complete" | "active";
}

export interface ThreadMessage {
  id: string;
  query: string;
  trajectory: TrajectoryStep[];
  result: QueryResponse | null;
  loading: boolean;
  error: string | null;
  timestamp: number;
}

export interface ThreadState {
  messages: ThreadMessage[];
  loading: boolean;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useQueryStream() {
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  /** Build context payload from prior messages (last 3 exchanges).
   *  Long assistant answers are summarized via /api/summarize. */
  async function buildContext(
    msgs: ThreadMessage[],
  ): Promise<{ role: string; content: string }[]> {
    const finished = msgs.filter((m) => m.result && !m.loading);
    const recent = finished.slice(-3);
    const turns: { role: string; content: string }[] = [];
    for (const m of recent) {
      turns.push({ role: "user", content: m.query.slice(0, 2000) });
      if (m.result?.answer) {
        const answer = m.result.answer;
        const content =
          answer.length > SUMMARIZE_THRESHOLD
            ? await summarizeText(answer)
            : answer;
        turns.push({ role: "assistant", content });
      }
    }
    return turns;
  }

  const submit = useCallback(
    async (req: QueryRequest) => {
      // Abort any in-flight stream
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const msgId = crypto.randomUUID();
      const newMessage: ThreadMessage = {
        id: msgId,
        query: req.query,
        trajectory: [],
        result: null,
        loading: true,
        error: null,
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, newMessage]);
      setLoading(true);

      // Build context from existing messages before we added the new one.
      // Summarizes long assistant answers via /api/summarize.
      const context = await buildContext(messages);

      try {
        const body: Record<string, unknown> = { ...req };
        if (context.length > 0) {
          body.context = context;
        }

        const res = await fetch(`${STREAM_BASE}/api/query/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: controller.signal,
        });

        if (!res.ok) {
          const detail = await res.text();
          throw new Error(`Stream failed (${res.status}): ${detail}`);
        }

        const reader = res.body?.getReader();
        if (!reader) throw new Error("No response body");

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split("\n\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data: ")) continue;

            const json = trimmed.slice(6);
            let event: Record<string, unknown>;
            try {
              event = JSON.parse(json);
            } catch {
              continue;
            }

            if (event.event === "step") {
              const step: TrajectoryStep = {
                step: event.step as number,
                node: event.node as string,
                label: event.label as string,
                detail: (event.detail as Record<string, unknown>) ?? {},
                status: "complete",
              };
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === msgId
                    ? { ...m, trajectory: [...m.trajectory, step] }
                    : m,
                ),
              );
            } else if (event.event === "result") {
              const raw = event.data as Record<string, unknown>;
              const mapped: QueryResponse = {
                query: raw.query as string,
                query_type: raw.query_type as string,
                tickers: raw.tickers as string[],
                answer: (raw.final_answer ?? raw.answer ?? "") as string,
                sources: raw.sources as QueryResponse["sources"],
                charts: (raw.retrieved_charts ??
                  raw.charts ??
                  []) as QueryResponse["charts"],
                anomalies: (raw.anomaly_scores ??
                  raw.anomalies ??
                  []) as QueryResponse["anomalies"],
                generated_charts: (raw.generated_charts ??
                  []) as QueryResponse["generated_charts"],
                web_sources: (raw.web_sources ??
                  []) as QueryResponse["web_sources"],
              };
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === msgId
                    ? { ...m, result: mapped, loading: false }
                    : m,
                ),
              );
            } else if (event.event === "error") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === msgId
                    ? {
                        ...m,
                        error:
                          (event.message as string) ?? "Unknown error",
                        loading: false,
                      }
                    : m,
                ),
              );
            }
          }
        }
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        const errorMsg =
          err instanceof Error ? err.message : "Stream connection failed";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId ? { ...m, error: errorMsg, loading: false } : m,
          ),
        );
      } finally {
        setLoading(false);
        // Mark message as done loading in case the stream ended without result event
        setMessages((prev) =>
          prev.map((m) =>
            m.id === msgId ? { ...m, loading: false } : m,
          ),
        );
      }
    },
    [messages],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setLoading(false);
    setMessages((prev) =>
      prev.map((m) => (m.loading ? { ...m, loading: false } : m)),
    );
  }, []);

  const clearThread = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setLoading(false);
  }, []);

  return { messages, loading, submit, cancel, clearThread } as const;
}
