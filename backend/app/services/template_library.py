from __future__ import annotations

import os
import re
from pathlib import Path

import defusedxml.ElementTree as ET

from app.core.database import DuckDBManager
from app.schemas.template import (
    ConstraintDef,
    FieldDef,
    RelationshipDef,
    Template,
    TemplateMeta,
    TemplateSummary,
)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_cache: dict[str, tuple[float, list[Template]]] = {}

# Only alphanumeric, spaces, dots, hyphens, underscores; must start with alphanumeric
_SAFE_TEMPLATE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9 ._\-]{0,79}$")


def _template_path(name: str) -> Path:
    """Return a safe filesystem path for a template name, raising on invalid input."""
    if not _SAFE_TEMPLATE_NAME.match(name):
        raise ValueError(
            f"Invalid template name {name!r}: must start with alphanumeric and "
            "contain only letters, digits, spaces, dots, hyphens, or underscores (max 80 chars)"
        )
    slug = re.sub(r"[^a-z0-9_]", "_", name.lower())
    path = (TEMPLATES_DIR / f"{slug}.xml").resolve()
    resolved_dir = TEMPLATES_DIR.resolve()
    if not str(path).startswith(str(resolved_dir) + os.sep):
        raise ValueError("Template path escapes the templates directory")
    return path


def _parse_field(element: ET.Element) -> FieldDef:
    constraint_elem = element.find("constraint")
    constraint: ConstraintDef | None = None
    if constraint_elem is not None:
        constraint = ConstraintDef(
            min=_safe_float(constraint_elem.get("min")),
            max=_safe_float(constraint_elem.get("max")),
            min_age=_safe_int(constraint_elem.get("min_age")),
            max_age=_safe_int(constraint_elem.get("max_age")),
            values=constraint_elem.get("values"),
            weights=constraint_elem.get("weights"),
            right_digits=_safe_int(constraint_elem.get("right_digits")),
            format=constraint_elem.get("format"),
            start=constraint_elem.get("start"),
            end=constraint_elem.get("end"),
        )
    return FieldDef(
        name=element.get("name", ""),
        type=element.get("type", "string"),
        generator=element.get("generator", "text"),
        unique=element.get("unique", "false").lower() == "true",
        formula=element.get("formula"),
        null_probability=_safe_float(element.get("null_probability")),
        constraint=constraint,
        condition=element.get("if"),
    )


def _safe_float(val: str | None) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val: str | None) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _parse_template_xml(xml_content: str) -> Template:
    root = ET.fromstring(xml_content)
    name = root.get("name", "Untitled")
    category = root.get("category", "General")

    meta_elem = root.find("meta")
    meta = TemplateMeta()
    if meta_elem is not None:
        meta.description = meta_elem.get("description", "")
        meta.version = meta_elem.get("version", "1.0")

    fields = [_parse_field(el) for el in root.findall("field")]
    relationships = [
        RelationshipDef(
            type=el.get("type", ""),
            source=el.get("source", ""),
            target=el.get("target"),
        )
        for el in root.findall("relationship")
    ]

    return Template(
        name=name,
        category=category,
        meta=meta,
        fields=fields,
        relationships=relationships,
    )


def _load_templates_from_disk() -> list[Template]:
    cached = _cache.get("templates")
    if cached is not None:
        cached_mtime, cached_templates = cached
        try:
            current_mtime = os.path.getmtime(TEMPLATES_DIR)
        except OSError:
            current_mtime = 0
        if current_mtime == cached_mtime:
            return cached_templates
    templates: list[Template] = []
    if not TEMPLATES_DIR.exists():
        _cache["templates"] = (0, templates)
        return templates
    for file_path in sorted(TEMPLATES_DIR.iterdir()):
        if file_path.suffix.lower() != ".xml":
            continue
        raw = file_path.read_text(encoding="utf-8")
        try:
            template = _parse_template_xml(raw)
            templates.append(template)
        except ET.ParseError as e:
            msg = f"Failed to parse {file_path.name}: {e}"
            raise RuntimeError(msg) from e
    try:
        mtime = os.path.getmtime(TEMPLATES_DIR)
    except OSError:
        mtime = 0
    _cache["templates"] = (mtime, templates)
    return templates


def _sync_to_duckdb(templates: list[Template]) -> None:
    db = DuckDBManager.get_instance()
    with db.transaction():
        db.execute("DELETE FROM metadata_templates")
        for t in templates:
            db.execute(
                "INSERT INTO metadata_templates (name, category, description, xml_content) VALUES (?, ?, ?, ?)",
                [t.name, t.category, t.meta.description, ""],
            )
    _cache.clear()


def list_templates() -> list[TemplateSummary]:
    templates = _load_templates_from_disk()
    return [
        TemplateSummary(
            name=t.name,
            category=t.category,
            description=t.meta.description,
            version=t.meta.version,
            field_count=len(t.fields),
        )
        for t in templates
    ]


def get_template(name: str) -> Template | None:
    templates = _load_templates_from_disk()
    for t in templates:
        if t.name == name:
            return t
    return None


def get_template_by_filename(filename: str) -> Template | None:
    file_path = (TEMPLATES_DIR / filename).resolve()
    if not str(file_path).startswith(str(TEMPLATES_DIR.resolve())):
        return None
    if not file_path.exists() or file_path.suffix.lower() != ".xml":
        return None
    raw = file_path.read_text(encoding="utf-8")
    try:
        return _parse_template_xml(raw)
    except ET.ParseError:
        return None


def create_template(xml_content: str) -> Template:
    template = _parse_template_xml(xml_content)
    file_path = _template_path(template.name)
    if file_path.exists():
        msg = f"Template '{template.name}' already exists"
        raise ValueError(msg)
    file_path.write_text(xml_content, encoding="utf-8")
    _sync_to_duckdb(_load_templates_from_disk())
    _cache.clear()
    return template


def update_template(name: str, xml_content: str) -> Template:
    template = _parse_template_xml(xml_content)
    old_path = _find_template_file(name)
    new_path = _template_path(template.name)
    if old_path and old_path != new_path:
        old_path.unlink()
    new_path.write_text(xml_content, encoding="utf-8")
    _sync_to_duckdb(_load_templates_from_disk())
    _cache.clear()
    return template


def delete_template(name: str) -> bool:
    file_path = _find_template_file(name)
    if file_path:
        file_path.unlink()
        _sync_to_duckdb(_load_templates_from_disk())
        _cache.clear()
        return True
    return False


def _find_template_file(name: str) -> Path | None:
    if not TEMPLATES_DIR.exists():
        return None
    for f in TEMPLATES_DIR.iterdir():
        if f.suffix.lower() != ".xml":
            continue
        raw = f.read_text(encoding="utf-8")
        try:
            root = ET.fromstring(raw)
            if root.get("name") == name:
                return f
        except ET.ParseError:
            continue
    return None


def _init_sample_templates() -> None:
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    _sync_to_duckdb(_load_templates_from_disk())
