import { useState } from "react";
import type { TransformResponse } from "../../types/transform";

const AGG_FUNCTIONS = [
  { value: "sum", label: "Sum" },
  { value: "avg", label: "Average" },
  { value: "min", label: "Minimum" },
  { value: "max", label: "Maximum" },
  { value: "count", label: "Count" },
  { value: "count_distinct", label: "Count Distinct" },
  { value: "first", label: "First" },
  { value: "last", label: "Last" },
];

interface AggregationDef {
  column: string;
  function: string;
  alias: string;
}

interface Props {
  datasetId: string;
  columns: string[];
  onResult: (result: TransformResponse) => void;
  onBack: () => void;
}

export default function AggregationPanel({
  datasetId,
  columns,
  onResult,
  onBack,
}: Props) {
  const [name, setName] = useState("");
  const [groupBy, setGroupBy] = useState<string[]>([]);
  const [aggregations, setAggregations] = useState<AggregationDef[]>([
    { column: "", function: "sum", alias: "" },
  ]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const toggleGroupBy = (col: string) => {
    setGroupBy((prev) =>
      prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col]
    );
  };

  const updateAgg = (
    idx: number,
    field: keyof AggregationDef,
    value: string
  ) => {
    setAggregations((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], [field]: value };
      if (field === "column" || field === "function") {
        next[idx].alias =
          field === "column"
            ? `${next[idx].function}_${value}`
            : `${value}_${next[idx].column}`;
      }
      return next;
    });
  };

  const addAgg = () => {
    setAggregations((prev) => [
      ...prev,
      { column: "", function: "sum", alias: "" },
    ]);
  };

  const removeAgg = (idx: number) => {
    setAggregations((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError("Result name is required");
      return;
    }
    if (groupBy.length === 0) {
      setError("Select at least one group-by column");
      return;
    }
    const validAggs = aggregations.filter((a) => a.column);
    if (validAggs.length === 0) {
      setError("Add at least one aggregation");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const res = await fetch(
        `/api/datasets/${datasetId}/aggregate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: name.trim(),
            group_by: groupBy,
            aggregations: validAggs,
          }),
        }
      );
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Aggregation failed");
      }
      const result = await res.json();
      onResult(result);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Aggregate</h3>
        <button
          onClick={onBack}
          className="text-sm text-indigo-400 hover:text-indigo-300"
        >
          &larr; Back to datasets
        </button>
      </div>

      <div>
        <label className="block text-sm font-medium text-[var(--text)] mb-1">
          Result name
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. revenue_by_country"
          className="w-full bg-[var(--elevated)] border border-[var(--border)] rounded px-3 py-2 text-sm"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-[var(--text)] mb-1">
          Group by columns
        </label>
        <div className="flex flex-wrap gap-2">
          {columns.map((col) => (
            <button
              key={col}
              onClick={() => toggleGroupBy(col)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                groupBy.includes(col)
                  ? "bg-indigo-600 text-white"
                  : "bg-[var(--elevated)] text-[var(--text)] hover:bg-[var(--elevated)]"
              }`}
            >
              {col}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-[var(--text)] mb-1">
          Aggregations
        </label>
        <div className="space-y-2">
          {aggregations.map((agg, idx) => (
            <div key={idx} className="flex gap-2 items-center">
              <select
                value={agg.column}
                onChange={(e) => updateAgg(idx, "column", e.target.value)}
                className="bg-[var(--elevated)] border border-[var(--border)] rounded px-2 py-1.5 text-sm flex-1"
              >
                <option value="">-- column --</option>
                {columns.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <select
                value={agg.function}
                onChange={(e) => updateAgg(idx, "function", e.target.value)}
                className="bg-[var(--elevated)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
              >
                {AGG_FUNCTIONS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
              <input
                type="text"
                value={agg.alias}
                onChange={(e) => updateAgg(idx, "alias", e.target.value)}
                placeholder="alias"
                className="bg-[var(--elevated)] border border-[var(--border)] rounded px-2 py-1.5 text-sm w-32"
              />
              {aggregations.length > 1 && (
                <button
                  onClick={() => removeAgg(idx)}
                  className="text-[var(--red)] hover:text-[var(--red)] text-sm px-1"
                >
                  x
                </button>
              )}
            </div>
          ))}
        </div>
        <button
          onClick={addAgg}
          className="mt-2 text-xs text-indigo-400 hover:text-indigo-300"
        >
          + Add aggregation
        </button>
      </div>

      {error && <p className="text-[var(--red)] text-sm">{error}</p>}

      <button
        onClick={handleSubmit}
        disabled={loading}
        className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:bg-[var(--elevated)] text-white font-medium py-2 px-4 rounded text-sm transition-colors"
      >
        {loading ? "Running..." : "Run Aggregation"}
      </button>
    </div>
  );
}
