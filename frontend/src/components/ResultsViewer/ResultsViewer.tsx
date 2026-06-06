import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { deleteDataset, fetchDatasetRows, fetchDatasets } from "../../api/datasets";
import AggregationPanel from "../AggregationPanel/AggregationPanel";
import DedupPanel from "../DedupPanel/DedupPanel";

export function ResultsViewer() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [mode, setMode] = useState<"data" | "aggregate" | "dedup">("data");
  const [exportOpen, setExportOpen] = useState(false);

  const list = useQuery({
    queryKey: ["datasets"],
    queryFn: fetchDatasets,
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  });

  const selectedMeta = list.data?.find((d) => d.dataset_id === selectedId);

  const rows = useQuery({
    queryKey: ["dataset-rows", selectedId, page],
    queryFn: () => fetchDatasetRows(selectedId!, page, 50),
    enabled: !!selectedId,
  });

  const deleteMut = useMutation({
    mutationFn: deleteDataset,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      if (selectedId) {
        setSelectedId(null);
        setPage(1);
      }
    },
    onError: (err) => {
      alert(err instanceof Error ? err.message : "Delete failed");
    },
  });

  const totalPages = rows.data ? Math.ceil(rows.data.total / 50) : 0;

  const handleTransformResult = () => {
    queryClient.invalidateQueries({ queryKey: ["datasets"] });
    setMode("data");
  };

  return (
    <div className="flex gap-6 h-full">
      <div className="w-64 shrink-0 flex flex-col gap-2">
        <h3 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider mb-1">
          Datasets
        </h3>
        {list.isPending && <p className="text-sm text-[var(--muted)]">Loading...</p>}
        {list.data && list.data.length === 0 && (
          <p className="text-sm text-[var(--muted)]">No datasets yet. Generate one!</p>
        )}
        <div className="flex flex-col gap-1 overflow-y-auto">
          {(list.data ?? []).map((ds) => (
            <div
              key={ds.dataset_id}
              onClick={() => {
                setSelectedId(ds.dataset_id);
                setPage(1);
                setMode("data");
              }}
              className={`px-3 py-2 rounded cursor-pointer text-sm transition-colors ${
                selectedId === ds.dataset_id
                  ? "bg-[var(--selection)] text-[var(--accent)] border border-[var(--accent)]"
                  : "text-[var(--muted)] hover:bg-[var(--elevated)] border border-transparent"
              }`}
            >
              <div className="truncate font-medium">{ds.name}</div>
              <div className="text-xs text-[var(--muted)] mt-0.5">
                {ds.row_count.toLocaleString()} rows ·{" "}
                {ds.columns.length} cols
              </div>
              <div className="text-xs text-[var(--muted)] font-mono">
                {ds.dataset_id}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 min-w-0 overflow-y-auto">
        {!selectedId && (
          <p className="text-sm text-[var(--muted)]">
            Select a dataset to preview its data
          </p>
        )}

        {selectedId && (
          <div className="flex flex-col gap-4">
            {/* Tab bar */}
            <div className="flex gap-1 border-b border-[var(--border)]">
              {(["data", "aggregate", "dedup"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`px-4 py-2 text-sm font-medium rounded-t transition-colors ${
                    mode === m
                      ? "bg-[var(--elevated)] text-[var(--text)] border border-b-transparent border-[var(--border)]"
                      : "text-[var(--muted)] hover:text-[var(--text)]"
                  }`}
                >
                  {m === "data"
                    ? "Data"
                    : m === "aggregate"
                      ? "Aggregate"
                      : "Dedup"}
                </button>
              ))}
            </div>

            {mode === "data" && rows.isPending && (
              <p className="text-sm text-[var(--muted)]">Loading data...</p>
            )}
            {mode === "data" && rows.error && (
              <p className="text-sm text-[var(--red)]">{rows.error.message}</p>
            )}

            {mode === "data" && rows.data && rows.data.meta && (
              <div className="flex flex-col gap-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-[var(--text)]">
                      {rows.data.meta.name}
                    </h2>
                    <p className="text-xs text-[var(--muted)]">
                      {rows.data.meta.row_count.toLocaleString()} rows ·{" "}
                      {rows.data.meta.columns.length} columns ·
                      h={rows.data.meta.homogeneity}%
                      {rows.data.meta.seed != null &&
                        ` · seed=${rows.data.meta.seed}`}
                    </p>
                  </div>
                  <div className="flex gap-2">
                  <div className="relative">
                      <button
                        onClick={() => setExportOpen(!exportOpen)}
                        onBlur={() => setTimeout(() => setExportOpen(false), 200)}
                        className="px-3 py-1 text-xs bg-[var(--elevated)] hover:bg-[var(--elevated)] rounded transition-colors"
                      >
                        Export ▾
                      </button>
                      {exportOpen && (
                        <div className="absolute right-0 top-full mt-1 bg-[var(--elevated)] border border-[var(--border)] rounded shadow-lg z-10">
                          <a
                            href={`/api/datasets/${selectedId}/export/csv`}
                            download
                            className="block px-4 py-2 text-xs text-[var(--text)] hover:bg-[var(--elevated)] whitespace-nowrap"
                            onClick={() => setExportOpen(false)}
                          >
                            CSV
                          </a>
                          <a
                            href={`/api/datasets/${selectedId}/export/parquet`}
                            download
                            className="block px-4 py-2 text-xs text-[var(--text)] hover:bg-[var(--elevated)] whitespace-nowrap"
                            onClick={() => setExportOpen(false)}
                          >
                            Parquet
                          </a>
                          <a
                            href={`/api/datasets/${selectedId}/export/xlsx`}
                            download
                            className="block px-4 py-2 text-xs text-[var(--text)] hover:bg-[var(--elevated)] whitespace-nowrap"
                            onClick={() => setExportOpen(false)}
                          >
                            XLSX
                          </a>
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => {
                        if (confirm("Delete this dataset?"))
                          deleteMut.mutate(selectedId!);
                      }}
                      className="px-3 py-1 text-xs bg-red-900/50 hover:bg-red-800/50 text-[var(--red)] rounded transition-colors"
                    >
                      Delete
                    </button>
                  </div>
                </div>

                <div className="overflow-x-auto border border-[var(--border)] rounded">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-[var(--surface)] text-left text-[var(--muted)] text-xs uppercase">
                        {rows.data.meta.columns.map((col) => (
                          <th
                            key={col}
                            className="px-3 py-2 font-medium whitespace-nowrap"
                          >
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="text-[var(--text)]">
                      {rows.data.rows.map((row, i) => (
                        <tr
                          key={i}
                          className="border-t border-[var(--border)] hover:bg-[var(--surface)]"
                        >
                          {rows.data!.meta!.columns.map((col) => (
                            <td
                              key={col}
                              className="px-3 py-1.5 whitespace-nowrap"
                            >
                              {String(row[col] ?? "")}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {totalPages > 1 && (
                  <div className="flex items-center justify-center gap-2 text-sm">
                    <button
                      onClick={() =>
                        setPage((p) => Math.max(1, p - 1))
                      }
                      disabled={page <= 1}
                      className="px-3 py-1 rounded bg-[var(--elevated)] hover:bg-[var(--elevated)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      Prev
                    </button>
                    <span className="text-[var(--muted)]">
                      Page {page} of {totalPages}
                    </span>
                    <button
                      onClick={() =>
                        setPage((p) => Math.min(totalPages, p + 1))
                      }
                      disabled={page >= totalPages}
                      className="px-3 py-1 rounded bg-[var(--elevated)] hover:bg-[var(--elevated)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      Next
                    </button>
                  </div>
                )}
              </div>
            )}

            {mode === "aggregate" && selectedMeta && (
              <AggregationPanel
                datasetId={selectedId}
                columns={selectedMeta.columns}
                onResult={handleTransformResult}
                onBack={() => setMode("data")}
              />
            )}

            {mode === "dedup" && selectedMeta && (
              <DedupPanel
                datasetId={selectedId}
                columns={selectedMeta.columns}
                onResult={handleTransformResult}
                onBack={() => setMode("data")}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function GenerationResults({
  results,
  onView,
}: {
  results: {
    dataset_id: string;
    name: string;
    table_name: string;
    row_count: number;
    columns: string[];
  }[];
  onView: () => void;
}) {
  return (
    <div className="border border-[var(--accent)] rounded p-4 bg-[var(--selection)]">
      <h3 className="text-sm font-semibold text-[var(--accent)] uppercase tracking-wider mb-3">
        Generation Complete
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {results.map((r) => (
          <div
            key={r.dataset_id}
            className="bg-[var(--surface)] border border-[var(--border)] rounded p-3"
          >
            <div className="text-sm font-medium text-[var(--text)]">{r.name}</div>
            <div className="text-xs text-[var(--muted)] font-mono mt-1">
              {r.table_name}
            </div>
            <div className="text-xs text-[var(--muted)] mt-0.5">
              {r.row_count.toLocaleString()} rows · {r.columns.length} cols
            </div>
            <div
              className="text-xs text-[var(--muted)] mt-1 truncate"
              title={r.columns.join(", ")}
            >
              {r.columns.join(", ")}
            </div>
          </div>
        ))}
      </div>
      <button
        onClick={onView}
        className="mt-3 px-4 py-1.5 text-sm bg-[var(--accent)] hover:bg-[var(--accent)] rounded transition-colors"
      >
        View in Datasets
      </button>
    </div>
  );
}
