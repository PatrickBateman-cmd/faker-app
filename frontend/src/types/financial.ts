export interface Quote {
  symbol: string;
  shortName: string;
  longName: string;
  regularMarketPrice: number;
  previousClose: number;
  change: number;
  changePercent: number;
  dayHigh: number;
  dayLow: number;
  volume: number;
  marketCap: number | null;
  currency: string;
}

export interface HistoryRecord {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface BatchRequest {
  symbols: string[];
  name?: string | null;
}

export interface BatchHistoryRequest {
  symbols: string[];
  period: string;
  interval: string;
  name?: string | null;
}

export interface DatasetResult {
  dataset_id: string;
  name: string;
  table_name: string;
  row_count: number;
  columns: string[];
}
