from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def check_condition(condition: str, row: list, fields: list) -> bool:
    if not condition:
        return True
    m = re.match(r'^\s*(\w+)\s*(>=|<=|!=|==|>|<)\s*(.+)\s*$', condition)
    if not m:
        return True
    field_name, op, raw_val = m.group(1), m.group(2), m.group(3).strip()

    field_indices = {f.name: i for i, f in enumerate(fields)}
    if field_name not in field_indices:
        return True

    field_val = row[field_indices[field_name]]
    if field_val is None:
        return False

    try:
        val = int(raw_val) if raw_val.isdigit() else (float(raw_val) if '.' in raw_val else raw_val.strip('"').strip("'"))
    except ValueError:
        val = raw_val.strip('"').strip("'")

    try:
        if op == ">=":
            return field_val >= val
        elif op == "<=":
            return field_val <= val
        elif op == ">":
            return field_val > val
        elif op == "<":
            return field_val < val
        elif op == "==":
            return field_val == val
        elif op == "!=":
            return field_val != val
        return True
    except TypeError:
        logger.warning("Type mismatch in condition '%s': %s vs %s", condition, type(field_val).__name__, type(val).__name__)
        return False
