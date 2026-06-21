import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  checkKaggleCredentials,
  importKaggleDataset,
  listKaggleFiles,
  searchKaggle,
} from "../../api/kaggle";
import type { KaggleDatasetItem, KaggleFile } from "../../types/kaggle";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function UsabilityBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  return (
    <div className="flex items-center gap-2 text-xs">
      <div className="flex-1 h-1.5 bg-[var(--elevated)] rounded-full overflow-hidden">
        <div
          className="h-full bg-[var(--accent)] rounded-full"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[var(--muted)] w-8 text-right">{pct}%</span>
    </div>
  );
}

function parseKaggleUrl(input: string): { owner: string; slug: string } | null {
  try {
    const url = new URL(input.trim());
    const m = url.pathname.match(/^\/datasets\/([^/]+)\/([^/]+)/);
    if (m) return { owner: m[1], slug: m[2] };
  } catch {
    const m = input.trim().match(/kaggle\.com\/datasets\/([^/]+)\/([^/]+)/);
    if (m) return { owner: m[1], slug: m[2] };
  }
  return null;
}

export function KagglePanel({ onNavigate }: { onNavigate?: (page: string) => void }) {
  const [searchInput, setSearchInput] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<KaggleDatasetItem | null>(null);
  const [importName, setImportName] = useState("");
  const [maxRows, setMaxRows] = useState("");
  const [importingFile, setImportingFile] = useState<string | null>(null);

  const credsQuery = useQuery({
    queryKey: ["kaggle-credentials"],
    queryFn: checkKaggleCredentials,
  });

  const searchQuery = useQuery({
    queryKey: ["kaggle-search", activeQuery, page],
    queryFn: () => searchKaggle(activeQuery, page),
    enabled: !!activeQuery,
  });

  const filesQuery = useQuery({
    queryKey: ["kaggle-files", selected?.ref],
    queryFn: () => {
      const [owner, slug] = selected!.ref.split("/");
      return listKaggleFiles(owner, slug);
    },
    enabled: !!selected,
  });

  const importMut = useMutation({ mutationFn: importKaggleDataset });

  function handleSearch() {
    const q = searchInput.trim();
    if (!q) return;
    const direct = parseKaggleUrl(q);
    if (direct) {
      setSelected({ ref: `${direct.owner}/${direct.slug}`, title: `${direct.owner}/${direct.slug}`, size: 0, last_updated: "", download_count: 0, vote_count: 0, usability_rating: 0, file_count: 0 });
      setActiveQuery("");
      importMut.reset();
      return;
    }
    setActiveQuery(q);
    setPage(1);
    setSelected(null);
    importMut.reset();
  }

  function handleImport(file: KaggleFile) {
    if (!selected) return;
    const [owner, slug] = selected.ref.split("/");
    setImportingFile(file.name);
    importMut.mutate({
      owner,
      slug,
      file_name: file.name,
      dataset_name: importName || undefined,
      max_rows: maxRows ? Number(maxRows) : undefined,
    });
  }

  const credsMissing = credsQuery.data && !credsQuery.data.configured;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold text-[var(--text)]">Kaggle Datasets</h2>
        {credsQuery.data && (
          <span
            className={`text-xs px-2 py-0.5 rounded-full ${
              credsQuery.data.configured
                ? "bg-[var(--selection)] text-[var(--green)]"
                : "bg-[var(--elevated)] text-[var(--red)]"
            }`}
          >
            {credsQuery.data.configured ? "Credentials OK" : "No credentials"}
          </span>
        )}
      </div>

      {credsMissing && (
        <div className="border border-[var(--red)] rounded-lg p-4 text-sm text-[var(--red)] bg-[var(--elevated)]">
          <p className="font-medium mb-1">Kaggle credentials not configured</p>
          <p className="text-[var(--muted)]">
            Set <code className="font-mono">KAGGLE_USERNAME</code> and{" "}
            <code className="font-mono">KAGGLE_KEY</code> environment variables, or create{" "}
            <code className="font-mono">~/.kaggle/kaggle.json</code> with your API token from
            kaggle.com/settings/account.
          </p>
        </div>
      )}

      {/* Search bar */}
      <div className="flex gap-3">
        <input
          className="flex-1 bg-[var(--elevated)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-700"
          placeholder="Search datasets or paste a kaggle.com/datasets/… URL"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleSearch(); }}
        />
        <button
          onClick={handleSearch}
          disabled={!searchInput.trim() || searchQuery.isFetching}
          className="px-4 py-2 bg-[var(--accent)] hover:opacity-90 disabled:opacity-40 text-white text-sm rounded transition-opacity"
        >
          {searchQuery.isFetching ? "Searching…" : "Search"}
        </button>
      </div>

      {searchQuery.error && (
        <p className="text-sm text-[var(--red)]">{(searchQuery.error as Error).message}</p>
      )}

      {/* Results grid */}
      {searchQuery.data && searchQuery.data.datasets.length > 0 && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <p className="text-xs text-[var(--muted)]">
              {searchQuery.data.total} results — click a dataset to browse its files
            </p>
            <div className="flex gap-2">
              <button
                disabled={page <= 1}
                onClick={() => { setPage((p) => p - 1); setSelected(null); }}
                className="px-2 py-1 text-xs bg-[var(--elevated)] rounded disabled:opacity-30 hover:bg-[var(--selection)]"
              >
                ← Prev
              </button>
              <span className="text-xs text-[var(--muted)] self-center">Page {page}</span>
              <button
                disabled={searchQuery.data.datasets.length < 20}
                onClick={() => { setPage((p) => p + 1); setSelected(null); }}
                className="px-2 py-1 text-xs bg-[var(--elevated)] rounded disabled:opacity-30 hover:bg-[var(--selection)]"
              >
                Next →
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-2">
            {searchQuery.data.datasets.map((ds) => (
              <button
                key={ds.ref}
                onClick={() => {
                  setSelected(ds.ref === selected?.ref ? null : ds);
                  importMut.reset();
                  setImportingFile(null);
                }}
                className={`text-left p-4 rounded-lg border transition-colors ${
                  selected?.ref === ds.ref
                    ? "border-[var(--accent)] bg-[var(--selection)]"
                    : "border-[var(--border)] bg-[var(--surface)] hover:border-[var(--accent)]"
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-[var(--text)] truncate">{ds.title}</p>
                    <p className="text-xs text-[var(--muted)] font-mono mt-0.5">{ds.ref}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-xs text-[var(--muted)]">{formatBytes(ds.size)}</p>
                    <p className="text-xs text-[var(--muted)]">{ds.file_count} file{ds.file_count !== 1 ? "s" : ""}</p>
                  </div>
                </div>
                <div className="mt-2 flex items-center gap-4 text-xs text-[var(--muted)]">
                  <span>↓ {ds.download_count.toLocaleString()}</span>
                  <span>▲ {ds.vote_count}</span>
                  <span className="flex-1">
                    <UsabilityBar score={ds.usability_rating} />
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {searchQuery.data?.datasets.length === 0 && (
        <p className="text-sm text-[var(--muted)]">No datasets found for "{activeQuery}".</p>
      )}

      {/* File browser */}
      {selected && (
        <div className="border-t border-[var(--border)] pt-5 mt-1">
          <h3 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider mb-3">
            Files in {selected.ref}
          </h3>

          {/* Import options */}
          <div className="flex gap-3 mb-4">
            <input
              value={importName}
              onChange={(e) => setImportName(e.target.value)}
              placeholder="Dataset name (optional)"
              className="flex-1 bg-[var(--elevated)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-700"
            />
            <input
              value={maxRows}
              onChange={(e) => setMaxRows(e.target.value.replace(/\D/g, ""))}
              placeholder="Max rows (optional)"
              className="w-36 bg-[var(--elevated)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-700"
            />
          </div>

          {filesQuery.isLoading && (
            <p className="text-sm text-[var(--muted)]">Loading files…</p>
          )}
          {filesQuery.error && (
            <p className="text-sm text-[var(--red)]">{(filesQuery.error as Error).message}</p>
          )}

          {filesQuery.data && filesQuery.data.length === 0 && (
            <p className="text-sm text-[var(--muted)]">No CSV files found in this dataset.</p>
          )}

          {filesQuery.data && filesQuery.data.length > 0 && (
            <div className="flex flex-col gap-2">
              {filesQuery.data.map((file: KaggleFile) => (
                <div
                  key={file.name}
                  className="flex items-center justify-between gap-4 p-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg"
                >
                  <div>
                    <p className="text-sm text-[var(--text)] font-mono">{file.name}</p>
                    <p className="text-xs text-[var(--muted)]">
                      {formatBytes(file.size)} · {file.creation_date.slice(0, 10)}
                    </p>
                  </div>
                  <button
                    onClick={() => handleImport(file)}
                    disabled={importMut.isPending && importingFile === file.name}
                    className="px-3 py-1.5 bg-[var(--accent)] hover:opacity-90 disabled:opacity-40 text-white text-xs rounded transition-opacity shrink-0"
                  >
                    {importMut.isPending && importingFile === file.name ? "Importing…" : "Import"}
                  </button>
                </div>
              ))}
            </div>
          )}

          {importMut.error && (
            <p className="text-sm text-[var(--red)] mt-3">{(importMut.error as Error).message}</p>
          )}

          {importMut.data && (
            <div className="mt-4 border border-[var(--accent)] rounded-lg p-4 bg-[var(--selection)]">
              <p className="text-sm text-[var(--accent)]">
                Imported <strong>{importMut.data.name}</strong> —{" "}
                {importMut.data.row_count.toLocaleString()} rows,{" "}
                {importMut.data.columns.length} columns
              </p>
              <button
                onClick={() => onNavigate?.("datasets")}
                className="mt-2 px-3 py-1 text-xs bg-[var(--accent)] hover:opacity-90 text-white rounded transition-opacity"
              >
                View in Datasets
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
