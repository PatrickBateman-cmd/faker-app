import type { ColumnInfo, DatasetMeta, DatasetRowResponse } from "../types/dataset";

const BASE = "/api/datasets";

export async function fetchDatasets(): Promise<DatasetMeta[]> {
  const res = await fetch(BASE);
  if (!res.ok) throw new Error("Failed to fetch datasets");
  return res.json();
}

export async function fetchDataset(id: string): Promise<DatasetMeta> {
  const res = await fetch(`${BASE}/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error("Dataset not found");
  return res.json();
}

export async function fetchDatasetRows(
  id: string,
  page = 1,
  perPage = 100,
): Promise<DatasetRowResponse> {
  const res = await fetch(
    `${BASE}/${encodeURIComponent(id)}/rows?page=${page}&per_page=${perPage}`,
  );
  if (!res.ok) throw new Error("Failed to fetch rows");
  return res.json();
}

export async function fetchDatasetColumns(id: string): Promise<ColumnInfo[]> {
  const res = await fetch(`${BASE}/${encodeURIComponent(id)}/columns`);
  if (!res.ok) throw new Error("Failed to fetch columns");
  return res.json();
}

export async function deleteDataset(id: string): Promise<void> {
  const res = await fetch(`${BASE}/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Delete failed");
}
