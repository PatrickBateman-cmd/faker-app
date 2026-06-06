import pytest
from app.core.validation import validate_column_name, validate_table_name


def test_valid_column_names():
    for name in ["name", "first_name", "col123", "_private"]:
        assert validate_column_name(name) == name


def test_invalid_column_names():
    for name in ["123name", "col-name", "col name", "DROP TABLE"]:
        with pytest.raises(ValueError, match="Invalid column name"):
            validate_column_name(name)


def test_valid_table_names():
    for name in ["dataset_abc123", "dataset_abc-def-123"]:
        assert validate_table_name(name) == name


def test_invalid_table_names():
    for name in ["my_table", "dataset_", "dataset_xyz!"]:
        with pytest.raises(ValueError, match="Invalid table name"):
            validate_table_name(name)
