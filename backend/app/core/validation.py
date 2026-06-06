import re

_VALID_COLUMN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_VALID_TABLE = re.compile(r"^dataset_[a-f0-9-]+$")


def validate_column_name(name: str) -> str:
    if not _VALID_COLUMN.match(name):
        raise ValueError(f"Invalid column name: {name!r}")
    return name


def validate_table_name(name: str) -> str:
    if not _VALID_TABLE.match(name):
        raise ValueError(f"Invalid table name: {name!r}")
    return name
