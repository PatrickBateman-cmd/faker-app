from __future__ import annotations

from pathlib import Path

import pytest

from app.services import template_library as tl

TEST_XML = """<template name="Product" category="Ecommerce">
  <meta description="Product template" version="1.0"/>
  <field name="product" type="string" generator="word"/>
  <field name="price" type="decimal" generator="pydecimal">
    <constraint min="1" max="999" right_digits="2"/>
  </field>
</template>"""


def test_list_templates(templates_dir):
    summaries = tl.list_templates()
    assert len(summaries) == 1
    s = summaries[0]
    assert s.name == "Person"
    assert s.category == "Basic"
    assert s.field_count == 2


def test_get_template(templates_dir):
    t = tl.get_template("Person")
    assert t is not None
    assert t.name == "Person"
    assert len(t.fields) == 2

    t = tl.get_template("NonExistent")
    assert t is None


def test_create_template(templates_dir):
    t = tl.create_template(TEST_XML)
    assert t.name == "Product"
    assert t.category == "Ecommerce"
    assert len(t.fields) == 2

    created = tl.get_template("Product")
    assert created is not None
    assert created.fields[0].name == "product"


def test_create_duplicate_template(templates_dir):
    tl.create_template(TEST_XML)
    with pytest.raises(ValueError, match="already exists"):
        tl.create_template(TEST_XML)


def test_delete_template(templates_dir):
    assert tl.delete_template("Person") is True
    assert tl.get_template("Person") is None

    assert tl.delete_template("NonExistent") is False


def test_list_after_create_and_delete(templates_dir):
    assert len(tl.list_templates()) == 1

    tl.create_template(TEST_XML)
    assert len(tl.list_templates()) == 2

    tl.delete_template("Product")
    assert len(tl.list_templates()) == 1


def test_get_template_by_filename(templates_dir):
    t = tl.get_template_by_filename("person.xml")
    assert t is not None
    assert t.name == "Person"

    t = tl.get_template_by_filename("nonexistent.xml")
    assert t is None
