import uuid as uuid_mod

from app.schemas.generation import ConstraintConfig, FieldDefinition
from app.services.generation_engine.sql_generators import SQL_GENERATOR_REGISTRY


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
