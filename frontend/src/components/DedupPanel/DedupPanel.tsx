import { useState } from "react";
import type { TransformResponse } from "../../types/transform";
import { useToast } from "../../hooks/useToast";

interface Props {
  datasetId: string;
  columns: string[];
  onResult: (result: TransformResponse) => void;
  onBack: () => void;
}

export default function DedupPanel({
  datasetId,
  columns,
  onResult,
  onBack,
}: Props) {
  const { addToast } = useToast();
  const [name, setName] = useState("");
  const [keys, setKeys] = useState<string[]>([]);
  const [strategy, setStrategy] = useState("keep_first");
  const [orderColumn, setOrderColumn] = useState("");
  const [orderDirection, setOrderDirection] = useState("desc");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const toggleKey = (col: string) => {
    setKeys((prev) =>
      prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col]
    );
  };

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError("Result name is required");
      return;
    }
    if (keys.length === 0) {
      setError("Select at least one key column");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const body: Record<string, unknown> = {
        name: name.trim(),
        keys,
        strategy,
      };
      if (orderColumn) {
        body.order_by = {
          column: orderColumn,
          direction: orderDirection,
        };
      }

      const res = await fetch(
        `/api/datasets/${datasetId}/dedup`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      );
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Dedup failed");
      }
      const result = await res.json();
      onResult(result);
      addToast("Dedup completed", "success");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      setError(msg);
      addToast(msg, "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Deduplicate</h3>
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
          placeholder="e.g. unique_customers"
          className="w-full bg-[var(--elevated)] border border-[var(--border)] rounded px-3 py-2 text-sm"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-[var(--text)] mb-1">
          Key columns (duplicates detected on)
        </label>
        <div className="flex flex-wrap gap-2">
          {columns.map((col) => (
            <button
              key={col}
              onClick={() => toggleKey(col)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                keys.includes(col)
                  ? "bg-emerald-600 text-white"
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
          Strategy
        </label>
        <select
          value={strategy}
          onChange={(e) => setStrategy(e.target.value)}
          className="w-full bg-[var(--elevated)] border border-[var(--border)] rounded px-3 py-2 text-sm"
        >
          <option value="keep_first">Keep First</option>
          <option value="keep_last">Keep Last</option>
          <option value="keep_none">Keep None (exclusive)</option>
        </select>
        <p className="text-xs text-[var(--muted)] mt-1">
          {strategy === "keep_none"
            ? "Remove rows that have any duplicate — only unique entries remain"
            : strategy === "keep_last"
              ? "Keep the last occurrence per key group"
              : "Keep the first occurrence per key group"}
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-[var(--text)] mb-1">
          Order by (determines which row to keep)
        </label>
        <div className="flex gap-2">
          <select
            value={orderColumn}
            onChange={(e) => setOrderColumn(e.target.value)}
            className="flex-1 bg-[var(--elevated)] border border-[var(--border)] rounded px-3 py-2 text-sm"
          >
            <option value="">-- column --</option>
            {columns.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <select
            value={orderDirection}
            onChange={(e) => setOrderDirection(e.target.value)}
            className="bg-[var(--elevated)] border border-[var(--border)] rounded px-3 py-2 text-sm"
          >
            <option value="desc">Desc</option>
            <option value="asc">Asc</option>
          </select>
        </div>
      </div>

      {error && <p className="text-[var(--red)] text-sm">{error}</p>}

      <button
        onClick={handleSubmit}
        disabled={loading}
        className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:bg-[var(--elevated)] text-white font-medium py-2 px-4 rounded text-sm transition-colors"
      >
        {loading ? "Running..." : "Run Dedup"}
      </button>
    </div>
  );
}
