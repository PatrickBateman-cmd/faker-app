from __future__ import annotations

import os
import tempfile
import shutil
from pathlib import Path

import pytest

from app.core.database import DuckDBManager


@pytest.fixture(autouse=True)
def cleanup_db():
    """Close any existing DuckDB instance before/after each test."""
    DuckDBManager.close_instance()
    yield
    try:
        DuckDBManager.close_instance()
    except Exception:
        pass


@pytest.fixture
def db():
    """Initialize DuckDB in a temp directory and return the manager."""
    tmpdir = tempfile.mkdtemp()
    mgr = DuckDBManager.initialize(db_path=tmpdir)
    yield mgr
    try:
        DuckDBManager.close_instance()
    except Exception:
        pass
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def client():
    """FastAPI TestClient with a fresh temp DB (lifespan runs)."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.config import settings

    DuckDBManager.close_instance()
    tmpdir = tempfile.mkdtemp()
    old_path = settings.duckdb_path
    settings.duckdb_path = tmpdir
    DuckDBManager.initialize(db_path=tmpdir)

    with TestClient(app) as c:
        yield c

    settings.duckdb_path = old_path
    try:
        DuckDBManager.close_instance()
    except Exception:
        pass
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def templates_dir(db):
    """Temp templates directory with a sample Person template loaded."""
    import app.services.template_library as tl

    original = tl.TEMPLATES_DIR
    tmpdir = tempfile.mkdtemp()
    tl.TEMPLATES_DIR = Path(tmpdir)

    sample = """<template name="Person" category="Basic">
  <meta description="Test template" version="1.0"/>
  <field name="name" type="string" generator="name"/>
  <field name="email" type="string" generator="email"/>
</template>"""
    (Path(tmpdir) / "person.xml").write_text(sample, encoding="utf-8")

    tl._sync_to_duckdb(tl._load_templates_from_disk())
    tl._cache.clear()
    yield Path(tmpdir)

    tl.TEMPLATES_DIR = original
    shutil.rmtree(tmpdir, ignore_errors=True)
