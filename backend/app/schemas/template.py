from pydantic import BaseModel, Field


class ConstraintDef(BaseModel):
    min: float | None = None
    max: float | None = None
    min_age: int | None = None
    max_age: int | None = None
    values: str | None = None
    weights: str | None = None
    right_digits: int | None = None
    format: str | None = None
    start: str | None = None
    end: str | None = None


class FieldDef(BaseModel):
    name: str
    type: str
    generator: str
    unique: bool = False
    formula: str | None = None
    null_probability: float | None = None
    constraint: ConstraintDef | None = None
    condition: str | None = None


class RelationshipDef(BaseModel):
    type: str
    source: str
    target: str | None = None


class TemplateMeta(BaseModel):
    description: str = ""
    version: str = "1.0"


class Template(BaseModel):
    name: str
    category: str = "General"
    meta: TemplateMeta = Field(default_factory=TemplateMeta)
    fields: list[FieldDef] = Field(default_factory=list)
    relationships: list[RelationshipDef] = Field(default_factory=list)


class TemplateSummary(BaseModel):
    name: str
    category: str
    description: str
    version: str
    field_count: int
