import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { fetchQuote, fetchHistory, batchFetchToDataset, fetchBatchHistory, enrichDataset } from "../../api/financial";
import { fetchDatasets, fetchDatasetColumns } from "../../api/datasets";
import type { DatasetMeta } from "../../types/dataset";
import type { ColumnInfo } from "../../types/dataset";

function formatNumber(n: number): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatMarketCap(n: number | null): string {
  if (n === null || n === undefined) return "—";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${formatNumber(n)}`;
}

const INTERVALS = [
  { value: "1m", label: "1 Minute" },
  { value: "5m", label: "5 Minutes" },
  { value: "15m", label: "15 Minutes" },
  { value: "30m", label: "30 Minutes" },
  { value: "60m", label: "60 Minutes" },
  { value: "1d", label: "1 Day" },
  { value: "5d", label: "5 Days" },
  { value: "1wk", label: "1 Week" },
  { value: "1mo", label: "1 Month" },
];

export function FinancialPanel({ onNavigate }: { onNavigate?: (page: string) => void }) {
  const [symbol, setSymbol] = useState("");
  const [input, setInput] = useState("");
  const [period, setPeriod] = useState("1mo");
  const [interval, setInterval] = useState("1d");

  const [batchInput, setBatchInput] = useState("AAPL, MSFT, GOOG, AMZN, TSLA");
  const [batchName, setBatchName] = useState("");
  const [batchMode, setBatchMode] = useState<"snapshot" | "history">("snapshot");
  const [batchPeriod, setBatchPeriod] = useState("1mo");
  const [batchInterval, setBatchInterval] = useState("1d");

  const [enrichDatasetId, setEnrichDatasetId] = useState("");
  const [enrichTickerCol, setEnrichTickerCol] = useState("");
  const [enrichName, setEnrichName] = useState("");
  const [enrichSelections, setEnrichSelections] = useState<Record<string, boolean>>({});

  const quote = useQuery({
    queryKey: ["financial", "quote", symbol],
    queryFn: () => fetchQuote(symbol),
    enabled: !!symbol,
  });

  const history = useQuery({
    queryKey: ["financial", "history", symbol, period, interval],
    queryFn: () => fetchHistory(symbol, period, interval),
    enabled: !!symbol,
  });

  const batchMut = useMutation({
    mutationFn: batchMode === "snapshot" ? batchFetchToDataset : fetchBatchHistory,
  });

  const datasetsQuery = useQuery({
    queryKey: ["datasets"],
    queryFn: fetchDatasets,
  });

  const columnsQuery = useQuery({
    queryKey: ["dataset-columns", enrichDatasetId],
    queryFn: () => fetchDatasetColumns(enrichDatasetId),
    enabled: !!enrichDatasetId,
  });

  const enrichMut = useMutation({
    mutationFn: enrichDataset,
  });

  const ENRICHMENT_OPTIONS = [
    { field_name: "regularMarketPrice", label: "Price" },
    { field_name: "change", label: "Change" },
    { field_name: "changePercent", label: "Change %" },
    { field_name: "previousClose", label: "Previous Close" },
    { field_name: "dayHigh", label: "Day High" },
    { field_name: "dayLow", label: "Day Low" },
    { field_name: "volume", label: "Volume" },
    { field_name: "marketCap", label: "Market Cap" },
    { field_name: "currency", label: "Currency" },
    { field_name: "shortName", label: "Short Name" },
    { field_name: "longName", label: "Long Name" },
  ];

  const periods = [
    { label: "1D", value: "1d" },
    { label: "5D", value: "5d" },
    { label: "1M", value: "1mo" },
    { label: "3M", value: "3mo" },
    { label: "6M", value: "6mo" },
    { label: "1Y", value: "1y" },
    { label: "2Y", value: "2y" },
    { label: "5Y", value: "5y" },
    { label: "YTD", value: "ytd" },
    { label: "Max", value: "max" },
  ];

  function handleBatchFetch() {
    const symbols = batchInput
      .split(/[,\n]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    if (symbols.length === 0) return;
    if (batchMode === "snapshot") {
      batchMut.mutate({ symbols, name: batchName || null });
    } else {
      batchMut.mutate({ symbols, period: batchPeriod, interval: batchInterval, name: batchName || null });
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Single symbol search */}
      <div className="flex items-center gap-3">
        <input
          className="bg-[var(--elevated)] border border-[var(--border)] rounded px-3 py-2 text-[var(--text)] text-sm w-40"
          placeholder="Symbol (e.g. AAPL)"
          value={input}
          onChange={(e) => setInput(e.target.value.toUpperCase())}
          onKeyDown={(e) => { if (e.key === "Enter") setSymbol(input); }}
        />
        <button
          onClick={() => setSymbol(input)}
          className="bg-[var(--accent)] hover:bg-[var(--accent)] text-white text-sm px-4 py-2 rounded transition-colors"
          disabled={!input.trim()}
        >
          Search
        </button>
        {quote.isPending && <span className="text-[var(--muted)] text-sm">Loading...</span>}
        {quote.error && (
          <span className="text-[var(--red)] text-sm">{quote.error.message}</span>
        )}
      </div>

      {/* Quote card */}
      {quote.data && (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5 flex flex-wrap items-end gap-8">
          <div>
            <h2 className="text-xl font-semibold text-[var(--text)]">
              {quote.data.shortName}
            </h2>
            {quote.data.longName && quote.data.longName !== quote.data.shortName && (
              <p className="text-sm text-[var(--muted)]">{quote.data.longName}</p>
            )}
            <p className="text-xs text-[var(--muted)] font-mono mt-1">{quote.data.symbol}</p>
          </div>
          <div className="text-right">
            <div className="text-3xl font-bold text-[var(--text)]">
              {formatNumber(quote.data.regularMarketPrice)}
            </div>
            <div
              className={`text-sm font-medium ${
                quote.data.change >= 0 ? "text-[var(--green)]" : "text-[var(--red)]"
              }`}
            >
              {quote.data.change >= 0 ? "+" : ""}
              {formatNumber(quote.data.change)} ({quote.data.changePercent >= 0 ? "+" : ""}
              {quote.data.changePercent}%)
            </div>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
            <div className="text-[var(--muted)]">Previous Close</div>
            <div className="text-[var(--text)] text-right">{formatNumber(quote.data.previousClose)}</div>
            <div className="text-[var(--muted)]">Day Range</div>
            <div className="text-[var(--text)] text-right">
              {formatNumber(quote.data.dayLow)} – {formatNumber(quote.data.dayHigh)}
            </div>
            <div className="text-[var(--muted)]">Volume</div>
            <div className="text-[var(--text)] text-right">
              {quote.data.volume.toLocaleString("en-US")}
            </div>
            <div className="text-[var(--muted)]">Market Cap</div>
            <div className="text-[var(--text)] text-right">
              {formatMarketCap(quote.data.marketCap)}
            </div>
            <div className="text-[var(--muted)]">Currency</div>
            <div className="text-[var(--text)] text-right">{quote.data.currency}</div>
          </div>
        </div>
      )}

      {/* Period selector + chart */}
      {history.data && history.data.length > 0 && (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider">
              Price History
            </h3>
            <div className="flex items-center gap-3">
              <select
                value={interval}
                onChange={(e) => setInterval(e.target.value)}
                className="bg-[var(--elevated)] text-[var(--text)] border border-[var(--border)] rounded px-2 py-1 text-xs"
              >
                {INTERVALS.map((i) => (
                  <option key={i.value} value={i.value}>{i.label}</option>
                ))}
              </select>
              <div className="flex gap-1">
                {periods.map((p) => (
                  <button
                    key={p.value}
                    onClick={() => setPeriod(p.value)}
                    className={`text-xs px-2 py-1 rounded transition-colors ${
                      period === p.value
                        ? "bg-[var(--selection)] text-[var(--accent)]"
                        : "text-[var(--muted)] hover:text-[var(--text)] hover:bg-[var(--elevated)]"
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={history.data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis
                dataKey="date"
                stroke="#6b7280"
                tick={{ fontSize: 11 }}
                tickFormatter={(d: string) => {
                  const parts = d.split("-");
                  return parts.length === 3 ? `${parts[1]}/${parts[2]}` : d;
                }}
              />
              <YAxis
                domain={["auto", "auto"]}
                stroke="#6b7280"
                tick={{ fontSize: 11 }}
                tickFormatter={(v: number) => formatNumber(v)}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#111827",
                  border: "1px solid #1f2937",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelStyle={{ color: "#9ca3af" }}
              />
              <Line
                type="monotone"
                dataKey="close"
                stroke="#06b6d4"
                strokeWidth={2}
                dot={false}
                name="Close"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* History table */}
      {history.data && history.data.length > 0 && (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5 overflow-x-auto">
          <h3 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider mb-3">
            Data Table
          </h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[var(--muted)] border-b border-[var(--border)]">
                <th className="pb-2 pr-4 font-medium">Date</th>
                <th className="pb-2 pr-4 font-medium">Open</th>
                <th className="pb-2 pr-4 font-medium">High</th>
                <th className="pb-2 pr-4 font-medium">Low</th>
                <th className="pb-2 pr-4 font-medium">Close</th>
                <th className="pb-2 font-medium">Volume</th>
              </tr>
            </thead>
            <tbody className="text-[var(--text)]">
              {[...history.data].reverse().map((r) => (
                <tr key={r.date} className="border-b border-[var(--border)] hover:bg-[var(--surface)]">
                  <td className="py-2 pr-4 text-[var(--muted)]">{r.date}</td>
                  <td className="py-2 pr-4">{formatNumber(r.open)}</td>
                  <td className="py-2 pr-4">{formatNumber(r.high)}</td>
                  <td className="py-2 pr-4">{formatNumber(r.low)}</td>
                  <td className="py-2 pr-4 font-medium text-[var(--text)]">{formatNumber(r.close)}</td>
                  <td className="py-2">{r.volume.toLocaleString("en-US")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Batch fetch section */}
      <div className="border-t border-[var(--border)] pt-6 mt-2">
        <h3 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider mb-3">
          Batch Fetch → Dataset
        </h3>

        {/* Snapshot / History toggle */}
        <div className="flex items-center gap-4 mb-4">
          <label className="flex items-center gap-2 text-sm text-[var(--text)] cursor-pointer">
            <input
              type="radio"
              name="batchMode"
              checked={batchMode === "snapshot"}
              onChange={() => setBatchMode("snapshot")}
              className="accent-[var(--accent)]"
            />
            Current Snapshot
          </label>
          <label className="flex items-center gap-2 text-sm text-[var(--text)] cursor-pointer">
            <input
              type="radio"
              name="batchMode"
              checked={batchMode === "history"}
              onChange={() => setBatchMode("history")}
              className="accent-[var(--accent)]"
            />
            Full History
          </label>
        </div>

        <div className="flex gap-4">
          <div className="flex-1 flex flex-col gap-2">
            <textarea
              value={batchInput}
              onChange={(e) => setBatchInput(e.target.value)}
              placeholder="Enter symbols separated by commas or newlines"
              rows={3}
              className="bg-[var(--elevated)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-700"
            />
            <input
              value={batchName}
              onChange={(e) => setBatchName(e.target.value)}
              placeholder="Dataset name (optional)"
              className="bg-[var(--elevated)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-700"
            />
            {batchMode === "history" && (
              <div className="flex gap-3">
                <select
                  value={batchPeriod}
                  onChange={(e) => setBatchPeriod(e.target.value)}
                  className="bg-[var(--elevated)] text-[var(--text)] border border-[var(--border)] rounded px-2 py-1.5 text-sm flex-1"
                >
                  {periods.map((p) => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </select>
                <select
                  value={batchInterval}
                  onChange={(e) => setBatchInterval(e.target.value)}
                  className="bg-[var(--elevated)] text-[var(--text)] border border-[var(--border)] rounded px-2 py-1.5 text-sm flex-1"
                >
                  {INTERVALS.map((i) => (
                    <option key={i.value} value={i.value}>{i.label}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
          <div className="flex flex-col justify-end gap-2">
            <button
              onClick={handleBatchFetch}
              disabled={batchMut.isPending}
              className="px-4 py-2 bg-[var(--accent)] hover:bg-[var(--accent)] disabled:bg-[var(--elevated)] disabled:text-[var(--muted)] text-white text-sm rounded transition-colors"
            >
              {batchMut.isPending ? "Fetching..." : "Fetch & Save"}
            </button>
          </div>
        </div>
        {batchMut.error && (
          <p className="text-sm text-[var(--red)] mt-2">{batchMut.error.message}</p>
        )}
        {batchMut.data && (
          <div className="mt-3 border border-[var(--accent)] rounded p-4 bg-[var(--selection)]">
            <p className="text-sm text-[var(--accent)]">
              Saved dataset: <strong>{batchMut.data.name}</strong> ({batchMut.data.row_count} rows, {batchMut.data.columns.length} cols)
            </p>
            <button
              onClick={() => onNavigate?.("datasets")}
              className="mt-2 px-3 py-1 text-xs bg-[var(--accent)] hover:bg-[var(--accent)] rounded transition-colors"
            >
              View in Datasets
            </button>
          </div>
        )}
      </div>

      {/* Enrich dataset section */}
      <div className="border-t border-[var(--border)] pt-6 mt-2">
        <h3 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider mb-3">
          Enrich Dataset
        </h3>
        <div className="flex flex-col gap-3">
          <div className="flex gap-4">
            <div className="flex-1 flex flex-col gap-2">
              <select
                value={enrichDatasetId}
                onChange={(e) => {
                  setEnrichDatasetId(e.target.value);
                  setEnrichTickerCol("");
                  setEnrichSelections({});
                }}
                className="bg-[var(--elevated)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text)]"
              >
                <option value="">Select dataset…</option>
                {datasetsQuery.data?.map((d: DatasetMeta) => (
                  <option key={d.dataset_id} value={d.dataset_id}>
                    {d.name}
                  </option>
                ))}
              </select>

              <select
                value={enrichTickerCol}
                onChange={(e) => setEnrichTickerCol(e.target.value)}
                disabled={!columnsQuery.data?.length}
                className="bg-[var(--elevated)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text)] disabled:opacity-50"
              >
                <option value="">Ticker column…</option>
                {columnsQuery.data?.map((c: ColumnInfo) => (
                  <option key={c.name} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </select>

              <input
                value={enrichName}
                onChange={(e) => setEnrichName(e.target.value)}
                placeholder="Result name (optional)"
                className="bg-[var(--elevated)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-700"
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            {ENRICHMENT_OPTIONS.map((opt) => (
              <label
                key={opt.field_name}
                className="flex items-center gap-1.5 text-sm text-[var(--text)] cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={!!enrichSelections[opt.field_name]}
                  onChange={(e) =>
                    setEnrichSelections((prev) => ({
                      ...prev,
                      [opt.field_name]: e.target.checked,
                    }))
                  }
                  className="accent-[var(--accent)]"
                />
                {opt.label}
              </label>
            ))}
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                const selected = ENRICHMENT_OPTIONS.filter(
                  (o) => enrichSelections[o.field_name]
                ).map((o) => ({ field_name: o.field_name, source: "quote" as const }));
                if (!enrichDatasetId || !enrichTickerCol || selected.length === 0) return;
                enrichMut.mutate({
                  source_dataset_id: enrichDatasetId,
                  ticker_column: enrichTickerCol,
                  enrichments: selected,
                  name: enrichName || undefined,
                });
              }}
              disabled={
                enrichMut.isPending ||
                !enrichDatasetId ||
                !enrichTickerCol ||
                !Object.values(enrichSelections).some(Boolean)
              }
              className="px-4 py-2 bg-[var(--accent)] hover:bg-[var(--accent)] disabled:bg-[var(--elevated)] disabled:text-[var(--muted)] text-white text-sm rounded transition-colors"
            >
              {enrichMut.isPending ? "Enriching..." : "Enrich"}
            </button>
            {enrichMut.isPending && (
              <span className="text-[var(--muted)] text-sm">Fetching quotes…</span>
            )}
          </div>

          {enrichMut.error && (
            <p className="text-sm text-[var(--red)]">{enrichMut.error.message}</p>
          )}

          {enrichMut.data && (
            <div className="border border-[var(--accent)] rounded p-4 bg-[var(--selection)]">
              <p className="text-sm text-[var(--accent)]">
                Enriched dataset: <strong>{enrichMut.data.name}</strong> ({enrichMut.data.row_count} rows, {enrichMut.data.columns.length} cols)
              </p>
              <button
                onClick={() => onNavigate?.("datasets")}
                className="mt-2 px-3 py-1 text-xs bg-[var(--accent)] hover:bg-[var(--accent)] rounded transition-colors"
              >
                View in Datasets
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
