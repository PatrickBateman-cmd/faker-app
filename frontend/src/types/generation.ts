import type { ConstraintDef as ConstraintConfig, FieldDef, TemplateSummary } from "./template";

export type { ConstraintConfig, FieldDef, TemplateSummary };

export interface GroupConfig {
  num_groups: number;
  split_pct: number;
  parent_fields: FieldDef[];
  child_fields: FieldDef[];
}

export interface DatasetDefinition {
  name: string;
  template?: string | null;
  rows: number;
  fields: FieldDef[];
  shared_key?: SharedKeyConfig | null;
  group_config?: GroupConfig | null;
}

export interface SharedKeyConfig {
  source_dataset: string;
  source_field: string;
}

export interface GenerateRequest {
  datasets: DatasetDefinition[];
  homogeneity: number;
  seed?: number | null;
  overlap_ratio?: number;
  exact_fields?: string[];
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
  overlap_pool_size: number;
  exact_fields: string[];
}
