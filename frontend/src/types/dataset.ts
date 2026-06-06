export interface DatasetMeta {
  dataset_id: string;
  name: string;
  table_name: string;
  row_count: number;
  columns: string[];
  homogeneity: number;
  seed: number | null;
  created_at: string | null;
}

export interface DatasetRowResponse {
  rows: Record<string, unknown>[];
  total: number;
  page: number;
  per_page: number;
  meta: DatasetMeta | null;
}

export interface ColumnInfo {
  name: string;
  type: string;
  dataset_id: string;
}
