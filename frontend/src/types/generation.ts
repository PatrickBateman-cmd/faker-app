import type { ConstraintDef as ConstraintConfig, FieldDef, TemplateSummary } from "./template";

export type { ConstraintConfig, FieldDef, TemplateSummary };

export interface DatasetDefinition {
  name: string;
  template?: string | null;
  rows: number;
  fields: FieldDef[];
  shared_key?: SharedKeyConfig | null;
}

export interface SharedKeyConfig {
  source_dataset: string;
  source_field: string;
}

export interface GenerateRequest {
  datasets: DatasetDefinition[];
  homogeneity: number;
  seed?: number | null;
}

export interface DatasetResult {
  dataset_id: string;
  name: string;
  table_name: string;
  row_count: number;
  columns: string[];
}

export interface GenerateResponse {
  run_id: number;
  homogeneity: number;
  seed: number | null;
  datasets: DatasetResult[];
}
