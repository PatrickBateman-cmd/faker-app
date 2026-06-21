export interface KaggleDatasetItem {
  ref: string;
  title: string;
  size: number;
  last_updated: string;
  download_count: number;
  vote_count: number;
  usability_rating: number;
  file_count: number;
}

export interface KaggleFile {
  name: string;
  size: number;
  creation_date: string;
}

export interface KaggleSearchResponse {
  datasets: KaggleDatasetItem[];
  total: number;
}

export interface KaggleImportRequest {
  owner: string;
  slug: string;
  file_name: string;
  dataset_name?: string;
  max_rows?: number;
}

export interface KaggleImportResponse {
  dataset_id: string;
  name: string;
  table_name: string;
  row_count: number;
  columns: string[];
}
