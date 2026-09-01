from app.schemas.generation import ConstraintConfig, FieldDefinition
from app.services.generation_engine.generators import GENERATOR_REGISTRY, generate_field_value
from faker import Faker


def test_registry_dispatch_for_email():
    fake = Faker()
    fake.seed_instance(1)
    field = FieldDefinition(name="e", generator="email", type="string")
    value = generate_field_value(fake, field, None)
    assert "@" in value


def test_unknown_generator_falls_back_to_word(caplog):
    fake = Faker()
    fake.seed_instance(1)
    field = FieldDefinition(name="mystery", generator="not_a_real_generator", type="string")
    with caplog.at_level("WARNING"):
        value = generate_field_value(fake, field, None)
    assert isinstance(value, str)
    assert "not_a_real_generator" not in GENERATOR_REGISTRY
    assert "Unknown generator" in caplog.text


def test_random_element_respects_weights():
    fake = Faker()
    field = FieldDefinition(name="status", generator="random_element", type="string")
    cons = ConstraintConfig(values="a,b", weights="100,0")
    results = {generate_field_value(fake, field, cons) for _ in range(20)}
    assert results == {"a"}
