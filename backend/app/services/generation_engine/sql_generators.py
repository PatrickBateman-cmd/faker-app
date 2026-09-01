from __future__ import annotations

from typing import Callable

from app.schemas.generation import ConstraintConfig, FieldDefinition


def _random_int_expr(cons: ConstraintConfig | None) -> tuple[str, list]:
    cmin = int(cons.min) if cons and cons.min is not None else 0
    cmax = int(cons.max) if cons and cons.max is not None else 999999
    return "CAST(FLOOR(random() * (? - ? + 1)) + ? AS BIGINT)", [cmax, cmin, cmin]


def _pydecimal_expr(cons: ConstraintConfig | None) -> tuple[str, list]:
    cmin = float(cons.min) if cons and cons.min is not None else 0.0
    cmax = float(cons.max) if cons and cons.max is not None else 999999.99
    right_digits = cons.right_digits if cons and cons.right_digits is not None else 2
    return "ROUND(? + random() * (? - ?), ?)", [cmin, cmax, cmin, right_digits]


def _boolean_expr(cons: ConstraintConfig | None) -> tuple[str, list]:
    return "(random() < 0.5)", []


def _uuid4_expr(cons: ConstraintConfig | None) -> tuple[str, list]:
    return "CAST(uuid() AS VARCHAR)", []


def _uuid_int_expr(cons: ConstraintConfig | None) -> tuple[str, list]:
    return "CAST(random() * 9223372036854775807 AS BIGINT)", []


SQL_GENERATOR_REGISTRY: dict[str, Callable[[ConstraintConfig | None], tuple[str, list]]] = {
    "random_int": _random_int_expr,
    "pyint": _random_int_expr,
    "pydecimal": _pydecimal_expr,
    "boolean": _boolean_expr,
    "uuid4": _uuid4_expr,
    "uuid_int": _uuid_int_expr,
}


def is_sql_eligible(field: FieldDefinition, exact_field_names: set[str]) -> bool:
    return (
        field.generator in SQL_GENERATOR_REGISTRY
        and not field.condition
        and field.generator not in ("formula", "shared_key")
        and field.name not in exact_field_names
    )


def build_sql_columns(
    db,
    fields: list[FieldDefinition],
    rows: int,
    field_seeds: dict[str, int | None],
) -> dict[str, list]:
    columns: dict[str, list] = {}
    for field in fields:
        template_fn = SQL_GENERATOR_REGISTRY[field.generator]
        expr, params = template_fn(field.constraint)
        seed = field_seeds.get(field.name)
        if seed is not None:
            seed_float = (seed % 2_000_000) / 1_000_000 - 1.0
            db.execute("SELECT setseed(?)", [seed_float])
        if field.null_probability:
            sql = f"SELECT CASE WHEN random() < ? THEN NULL ELSE {expr} END FROM range(?)"
            full_params = [field.null_probability, *params, rows]
        else:
            sql = f"SELECT {expr} FROM range(?)"
            full_params = [*params, rows]
        result = db.execute(sql, full_params).fetchall()
        columns[field.name] = [r[0] for r in result]
    return columns
