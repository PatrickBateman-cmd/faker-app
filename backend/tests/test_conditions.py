from app.schemas.generation import FieldDefinition
from app.services.generation_engine.conditions import check_condition


def _fields():
    return [FieldDefinition(name="age", generator="random_int", type="integer")]


def test_condition_true_when_satisfied():
    assert check_condition("age >= 18", [21], _fields()) is True


def test_condition_false_when_not_satisfied():
    assert check_condition("age >= 18", [10], _fields()) is False


def test_condition_not_equal():
    assert check_condition("age != 10", [21], _fields()) is True
    assert check_condition("age != 10", [10], _fields()) is False


def test_condition_none_value_is_false():
    assert check_condition("age >= 18", [None], _fields()) is False


def test_unrecognized_condition_string_defaults_true():
    assert check_condition("not a real condition", [21], _fields()) is True


def test_empty_condition_defaults_true():
    assert check_condition("", [21], _fields()) is True
