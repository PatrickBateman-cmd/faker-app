from pydantic import BaseModel, Field


class ConstraintConfig(BaseModel):
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


class FieldDefinition(BaseModel):
    name: str
    generator: str
    type: str = "string"
    unique: bool = False
    formula: str | None = None
    null_probability: float | None = None
    constraint: ConstraintConfig | None = None
    condition: str | None = None


class SharedKeyConfig(BaseModel):
    source_dataset: str
    source_field: str


class GroupConfig(BaseModel):
    num_groups: int = Field(..., ge=1, le=10000)
    split_pct: float = Field(default=100, ge=1, le=100)
    parent_fields: list[FieldDefinition]
    child_fields: list[FieldDefinition]


class DatasetDefinition(BaseModel):
    name: str
    template: str | None = None
    rows: int = Field(default=100, ge=1, le=100000)
    fields: list[FieldDefinition] = Field(default_factory=list)
    shared_key: SharedKeyConfig | None = None
    group_config: GroupConfig | None = None


class GenerateRequest(BaseModel):
    datasets: list[DatasetDefinition] = Field(
        ..., min_length=1, max_length=4
    )
    homogeneity: int = Field(default=50, ge=1, le=100)
    seed: int | None = None


class DatasetResult(BaseModel):
    dataset_id: str
    name: str
    table_name: str
    row_count: int
    columns: list[str]


class GenerateResponse(BaseModel):
    run_id: int
    homogeneity: int
    seed: int | None
    datasets: list[DatasetResult]
