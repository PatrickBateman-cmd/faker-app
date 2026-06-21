import type {
  KaggleSearchResponse,
  KaggleFile,
  KaggleImportRequest,
  KaggleImportResponse,
} from "../types/kaggle";

export async function checkKaggleCredentials(): Promise<{ configured: boolean }> {
  const res = await fetch("/api/kaggle/credentials");
  if (!res.ok) throw new Error("Failed to check credentials");
  return res.json();
}

export async function searchKaggle(
  q: string,
  page = 1,
  perPage = 20
): Promise<KaggleSearchResponse> {
  const params = new URLSearchParams({ q, page: String(page), per_page: String(perPage) });
  const res = await fetch(`/api/kaggle/search?${params}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Search failed");
  }
  return res.json();
}

export async function listKaggleFiles(owner: string, slug: string): Promise<KaggleFile[]> {
  const res = await fetch(`/api/kaggle/datasets/${encodeURIComponent(owner)}/${encodeURIComponent(slug)}/files`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to list files");
  }
  return res.json();
}

export async function importKaggleDataset(body: KaggleImportRequest): Promise<KaggleImportResponse> {
  const res = await fetch("/api/kaggle/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Import failed");
  }
  return res.json();
}
