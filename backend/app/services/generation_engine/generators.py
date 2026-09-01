from __future__ import annotations

import logging
import random
import uuid
from typing import Callable

from faker import Faker

from app.schemas.generation import ConstraintConfig, FieldDefinition

logger = logging.getLogger(__name__)


def apply_constraint(fake: Faker, value: object, constraint: ConstraintConfig | None) -> object:
    if constraint is None:
        return value
    if isinstance(value, (int, float)):
        cmin = constraint.min if constraint.min is not None else float("-inf")
        cmax = constraint.max if constraint.max is not None else float("inf")
        if isinstance(value, float) and constraint.right_digits is not None:
            value = round(value, constraint.right_digits)
        return max(cmin, min(cmax, value))
    return value


def _random_element(fake: Faker, cons: ConstraintConfig | None) -> object:
    if cons and cons.values:
        vals = [v.strip() for v in cons.values.split(",")]
        if cons.weights:
            weights = [float(w.strip()) for w in cons.weights.split(",")]
            return random.choices(vals, weights=weights, k=1)[0]
        return fake.random_element(vals)
    return fake.word()


GENERATOR_REGISTRY: dict[str, Callable[[Faker, ConstraintConfig | None], object]] = {
    "first_name": lambda fake, cons: fake.first_name(),
    "last_name": lambda fake, cons: fake.last_name(),
    "name": lambda fake, cons: fake.name(),
    "email": lambda fake, cons: fake.email(),
    "phone_number": lambda fake, cons: fake.phone_number(),
    "job": lambda fake, cons: fake.job(),
    "company": lambda fake, cons: fake.company(),
    "company_suffix": lambda fake, cons: fake.company_suffix(),
    "catch_phrase": lambda fake, cons: fake.catch_phrase(),
    "domain_name": lambda fake, cons: fake.domain_name(),
    "url": lambda fake, cons: fake.url(),
    "country": lambda fake, cons: fake.country(),
    "country_code": lambda fake, cons: fake.country_code(),
    "city": lambda fake, cons: fake.city(),
    "street_address": lambda fake, cons: fake.street_address(),
    "zipcode": lambda fake, cons: fake.zipcode(),
    "text": lambda fake, cons: fake.text(max_nb_chars=int(cons.max) if cons and cons.max else 100),
    "boolean": lambda fake, cons: fake.boolean(),
    "random_int": lambda fake, cons: fake.random_int(
        min=int(cons.min) if cons and cons.min is not None else 0,
        max=int(cons.max) if cons and cons.max is not None else 999999,
    ),
    "pyint": lambda fake, cons: fake.random_int(
        min=int(cons.min) if cons and cons.min is not None else 0,
        max=int(cons.max) if cons and cons.max is not None else 999999,
    ),
    "pydecimal": lambda fake, cons: float(
        fake.pydecimal(
            min_value=float(cons.min) if cons and cons.min is not None else 0.0,
            max_value=float(cons.max) if cons and cons.max is not None else 999999.99,
            right_digits=cons.right_digits if cons and cons.right_digits is not None else 2,
        )
    ),
    "bothify": lambda fake, cons: fake.bothify(text=cons.format if cons and cons.format else "?????#####"),
    "random_element": _random_element,
    "currency_code": lambda fake, cons: fake.currency_code(),
    "swift": lambda fake, cons: fake.swift8(),
    "iban": lambda fake, cons: fake.iban(),
    "bban": lambda fake, cons: fake.bban(),
    "date_between": lambda fake, cons: fake.date_between(
        start_date=cons.start if cons and cons.start else "-5y",
        end_date=cons.end if cons and cons.end else "today",
    ).isoformat(),
    "date_of_birth": lambda fake, cons: fake.date_of_birth(
        minimum_age=cons.min_age if cons and cons.min_age is not None else 18,
        maximum_age=cons.max_age if cons and cons.max_age is not None else 99,
    ).isoformat(),
    "date_time": lambda fake, cons: fake.date_time().isoformat(),
    "word": lambda fake, cons: fake.word(),
}


def generate_field_value(fake: Faker, field: FieldDefinition, constraint: ConstraintConfig | None) -> object:
    gen = field.generator
    cons = constraint or field.constraint

    if gen == "uuid4":
        return str(uuid.uuid4())
    if gen == "uuid_int":
        return uuid.uuid4().int & ((1 << 63) - 1)
    if gen == "formula":
        return apply_constraint(fake, field.formula or "", cons)
    if gen == "shared_key":
        return apply_constraint(fake, "", cons)

    handler = GENERATOR_REGISTRY.get(gen)
    if handler is None:
        logger.warning("Unknown generator '%s' for field '%s', falling back to fake.word()", gen, field.name)
        return apply_constraint(fake, fake.word(), cons)
    return apply_constraint(fake, handler(fake, cons), cons)
