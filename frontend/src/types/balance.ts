import type { FieldBreakConfig } from "./generation";

export interface BalanceDeriveRequest {
  name: string;
  account_fields: string[];
  currency_field?: string;
  date_field?: string;
  amount_field?: string;
  direction_field?: string;
  credit_values?: string[];
  debit_values?: string[];
  start_date?: string | null;
  end_date?: string | null;
  opening_balance_seed?: number | null;
  balance_breaks?: FieldBreakConfig[];
}

export interface BalanceDeriveResponse {
  dataset_id: string;
  name: string;
  table_name: string;
  row_count: number;
  columns: string[];
  source_dataset: string;
  transform_type: string;
  opening_balance_seed: number;
  start_date: string;
  end_date: string;
  run_id: number | null;
  break_count: number;
}
