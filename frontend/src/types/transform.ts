export interface TransformResponse {
  dataset_id: string;
  name: string;
  table_name: string;
  row_count: number;
  columns: string[];
  source_dataset: string;
  transform_type: string;
}
