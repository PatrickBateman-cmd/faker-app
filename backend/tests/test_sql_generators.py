import uuid as uuid_mod

from app.schemas.generation import ConstraintConfig, FieldDefinition
from app.services.generation_engine.sql_generators import (
    SQL_GENERATOR_REGISTRY,
    build_sql_columns,
    is_sql_eligible,
)


def test_registry_has_v1_generators():
    assert set(SQL_GENERATOR_REGISTRY.keys()) == {
        "random_int", "pyint", "pydecimal", "boolean", "uuid4", "uuid_int",
    }


def test_random_int_expr_bounds(db):
    expr, params = SQL_GENERATOR_REGISTRY["random_int"](ConstraintConfig(min=5, max=10))
    sql = f"SELECT {expr} FROM range(?)"
    rows = db.execute(sql, [*params, 200]).fetchall()
    values = [r[0] for r in rows]
    assert len(values) == 200
    assert all(isinstance(v, int) for v in values)
    assert all(5 <= v <= 10 for v in values)


def test_random_int_default_bounds(db):
    expr, params = SQL_GENERATOR_REGISTRY["random_int"](None)
    sql = f"SELECT {expr} FROM range(?)"
    rows = db.execute(sql, [*params, 50]).fetchall()
    assert all(0 <= r[0] <= 999999 for r in rows)


def test_pydecimal_expr_bounds_and_rounding(db):
    expr, params = SQL_GENERATOR_REGISTRY["pydecimal"](
        ConstraintConfig(min=0, max=100, right_digits=2)
    )
    sql = f"SELECT {expr} FROM range(?)"
    rows = db.execute(sql, [*params, 100]).fetchall()
    for (v,) in rows:
        assert 0 <= v <= 100
        assert round(v, 2) == v


def test_boolean_expr_type(db):
    expr, params = SQL_GENERATOR_REGISTRY["boolean"](None)
    sql = f"SELECT {expr} FROM range(?)"
    rows = db.execute(sql, [*params, 50]).fetchall()
    assert all(isinstance(r[0], bool) for r in rows)


def test_uuid4_expr_format(db):
    expr, params = SQL_GENERATOR_REGISTRY["uuid4"](None)
    sql = f"SELECT {expr} FROM range(?)"
    rows = db.execute(sql, [*params, 20]).fetchall()
    for (v,) in rows:
        uuid_mod.UUID(v)  # raises ValueError if malformed


def test_uuid_int_expr_range(db):
    expr, params = SQL_GENERATOR_REGISTRY["uuid_int"](None)
    sql = f"SELECT {expr} FROM range(?)"
    rows = db.execute(sql, [*params, 50]).fetchall()
    for (v,) in rows:
        assert isinstance(v, int)
        assert 0 <= v < (1 << 63)


def test_eligible_plain_field():
    field = FieldDefinition(name="n", generator="random_int", type="integer")
    assert is_sql_eligible(field, set()) is True


def test_ineligible_condition():
    field = FieldDefinition(name="n", generator="random_int", type="integer", condition="age >= 18")
    assert is_sql_eligible(field, set()) is False


def test_ineligible_exact_field():
    field = FieldDefinition(name="n", generator="random_int", type="integer")
    assert is_sql_eligible(field, {"n"}) is False


def test_ineligible_non_sql_generator():
    field = FieldDefinition(name="e", generator="email", type="string")
    assert is_sql_eligible(field, set()) is False


def test_ineligible_shared_key():
    field = FieldDefinition(name="sk", generator="shared_key", type="string")
    assert is_sql_eligible(field, set()) is False


def test_ineligible_formula():
    field = FieldDefinition(name="fm", generator="formula", type="string", formula="{{x}}")
    assert is_sql_eligible(field, set()) is False


def test_build_sql_columns_returns_all_fields(db):
    fields = [
        FieldDefinition(name="n", generator="random_int", type="integer",
                         constraint=ConstraintConfig(min=1, max=10)),
        FieldDefinition(name="ok", generator="boolean", type="boolean"),
    ]
    columns = build_sql_columns(db, fields, 30, {"n": None, "ok": None})
    assert set(columns.keys()) == {"n", "ok"}
    assert len(columns["n"]) == 30
    assert len(columns["ok"]) == 30
    assert all(1 <= v <= 10 for v in columns["n"])


def test_build_sql_columns_null_probability(db):
    field = FieldDefinition(name="n", generator="random_int", type="integer",
                             constraint=ConstraintConfig(min=1, max=10), null_probability=1.0)
    columns = build_sql_columns(db, [field], 30, {"n": None})
    assert all(v is None for v in columns["n"])


def test_build_sql_columns_null_probability_partial(db):
    field = FieldDefinition(name="n", generator="random_int", type="integer",
                             constraint=ConstraintConfig(min=1, max=10), null_probability=0.5)
    columns = build_sql_columns(db, [field], 500, {"n": None})
    none_count = sum(1 for v in columns["n"] if v is None)
    assert 150 < none_count < 350  # ~50% of 500, generous tolerance


def test_build_sql_columns_determinism_same_seed(db):
    field = FieldDefinition(name="n", generator="random_int", type="integer",
                             constraint=ConstraintConfig(min=1, max=1000000))
    a = build_sql_columns(db, [field], 20, {"n": 12345})
    b = build_sql_columns(db, [field], 20, {"n": 12345})
    assert a == b


def test_build_sql_columns_different_seed_differs(db):
    field = FieldDefinition(name="n", generator="random_int", type="integer",
                             constraint=ConstraintConfig(min=1, max=1000000))
    a = build_sql_columns(db, [field], 20, {"n": 111})
    b = build_sql_columns(db, [field], 20, {"n": 222})
    assert a != b
