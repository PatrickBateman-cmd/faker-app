import type { Quote, HistoryRecord, BatchRequest, BatchHistoryRequest, DatasetResult } from "../types/financial";
import type { TransformResponse } from "../types/transform";

export interface EnrichmentDef {
  field_name: string;
  source: "quote" | "info";
}

export interface EnrichRequest {
  source_dataset_id: string;
  ticker_column: string;
  enrichments: EnrichmentDef[];
  name?: string;
}

export async function fetchQuote(symbol: string): Promise<Quote> {
  const res = await fetch(`/api/financial/quote?symbol=${encodeURIComponent(symbol)}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to fetch quote");
  }
  return res.json();
}

export async function fetchHistory(
  symbol: string,
  period = "1mo",
  interval = "1d"
): Promise<HistoryRecord[]> {
  const res = await fetch(
    `/api/financial/history?symbol=${encodeURIComponent(symbol)}&period=${encodeURIComponent(period)}&interval=${encodeURIComponent(interval)}`
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to fetch history");
  }
  return res.json();
}

export async function fetchBatchHistory(body: BatchHistoryRequest): Promise<DatasetResult> {
  const res = await fetch("/api/financial/batch-history", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Batch history fetch failed");
  }
  return res.json();
}

export async function enrichDataset(body: EnrichRequest): Promise<TransformResponse> {
  const res = await fetch("/api/financial/enrich", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Enrich failed" }));
    throw new Error(err.detail);
  }
  return res.json();
}

export async function batchFetchToDataset(body: BatchRequest): Promise<DatasetResult> {
  const res = await fetch("/api/financial/batch-to-dataset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Batch fetch failed");
  }
  return res.json();
}
