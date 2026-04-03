"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { QueryRequest, QueryResponse } from "./api";

const STREAM_BASE =
  process.env.NEXT_PUBLIC_STREAM_URL ?? "http://localhost:8000";

/** Threshold above which assistant answers get summarized instead of truncated. */
const SUMMARIZE_THRESHOLD = 1500;

/** If no SSE event arrives for this long, treat the stream as timed out. */
const STREAM_TIMEOUT_MS = 300_000; // 5 minutes

/** localStorage key for persisted thread. */
const STORAGE_KEY = "secsignal-thread";

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
  duration_ms?: number;
  started_at?: number;
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
// localStorage helpers
// ---------------------------------------------------------------------------

function loadThread(): ThreadMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ThreadMessage[];
    // Strip any messages that were mid-loading when the page closed
    return parsed
      .filter((m) => !m.loading)
      .map((m) => ({ ...m, loading: false }));
  } catch {
    return [];
  }
}

function saveThread(messages: ThreadMessage[]) {
  if (typeof window === "undefined") return;
  try {
    // Only persist completed messages
    const completed = messages.filter((m) => !m.loading);
    if (completed.length === 0) {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(completed));
    }
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useQueryStream() {
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hydrated = useRef(false);

  // Hydrate from localStorage on mount (only once)
  useEffect(() => {
    if (!hydrated.current) {
      hydrated.current = true;
      const saved = loadThread();
      if (saved.length > 0) {
        setMessages(saved);
      }
    }
  }, []);

  // Persist to localStorage whenever messages change (skip loading messages)
  useEffect(() => {
    if (hydrated.current) {
      saveThread(messages);
    }
  }, [messages]);

  /** Reset the inactivity timeout. */
  function resetTimeout(msgId: string) {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => {
      abortRef.current?.abort();
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId && m.loading
            ? {
                ...m,
                error: "Analysis timed out — no response received for 90 seconds. Please try again.",
                loading: false,
              }
            : m,
        ),
      );
      setLoading(false);
    }, STREAM_TIMEOUT_MS);
  }

  function clearTimeoutRef() {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }

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
      clearTimeoutRef();
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
      const context = await buildContext(messages);

      // Start inactivity timeout
      resetTimeout(msgId);

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

          // Reset timeout on every chunk received
          resetTimeout(msgId);

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
                duration_ms: (event.duration_ms as number) ?? undefined,
                started_at: (event.started_at as number) ?? undefined,
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
                follow_up_questions: (raw.follow_up_questions ??
                  []) as string[],
                confidence_score: (raw.confidence_score ?? 0) as number,
                confidence_factors: (raw.confidence_factors ??
                  {}) as Record<string, unknown>,
              };
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === msgId
                    ? { ...m, result: mapped, loading: false }
                    : m,
                ),
              );
            } else if (event.event === "guardrail_rejected") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === msgId
                    ? {
                        ...m,
                        error:
                          (event.message as string) ??
                          "This query is outside the scope of SEC filing analysis. Please ask about financial data, company filings, or market trends.",
                        loading: false,
                      }
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
        clearTimeoutRef();
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
    clearTimeoutRef();
    setLoading(false);
    setMessages((prev) =>
      prev.map((m) =>
        m.loading
          ? { ...m, loading: false, error: "Analysis cancelled." }
          : m,
      ),
    );
  }, []);

  /** Retry the last failed message by resubmitting its query. */
  const retry = useCallback(
    (messageId: string) => {
      const target = messages.find((m) => m.id === messageId);
      if (!target) return;
      // Remove the failed message and resubmit
      setMessages((prev) => prev.filter((m) => m.id !== messageId));
      submit({ query: target.query });
    },
    [messages, submit],
  );

  const clearThread = useCallback(() => {
    abortRef.current?.abort();
    clearTimeoutRef();
    setMessages([]);
    setLoading(false);
    if (typeof window !== "undefined") {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  return { messages, loading, submit, cancel, retry, clearThread } as const;
}
