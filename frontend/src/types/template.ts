export interface TemplateSummary {
  name: string;
  category: string;
  description: string;
  version: string;
  field_count: number;
}

export interface ConstraintDef {
  min?: number | null;
  max?: number | null;
  min_age?: number | null;
  max_age?: number | null;
  values?: string | null;
  right_digits?: number | null;
  format?: string | null;
  start?: string | null;
  end?: string | null;
}

export interface FieldDef {
  name: string;
  type: string;
  generator: string;
  unique: boolean;
  formula?: string | null;
  constraint?: ConstraintDef | null;
}

export interface RelationshipDef {
  type: string;
  source: string;
  target?: string | null;
}

export interface TemplateMeta {
  description: string;
  version: string;
}

export interface Template {
  name: string;
  category: string;
  meta: TemplateMeta;
  fields: FieldDef[];
  relationships: RelationshipDef[];
}
