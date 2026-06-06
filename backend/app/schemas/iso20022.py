from pydantic import BaseModel


class DomainInfo(BaseModel):
    id: str
    name: str


class MessageInfo(BaseModel):
    message_id: str
    message_name: str
    submitting_org: str
    business_area: str
    xsd_url: str | None = None


class ParsedField(BaseModel):
    name: str
    xsd_type: str
    mapped_generator: str
    min_occurs: int = 1
    max_occurs: str = "1"
    documentation: str | None = None
    enumeration_values: list[str] | None = None
    nested_fields: list[ParsedField] | None = None


class XsdParsedResponse(BaseModel):
    message_id: str
    message_name: str
    namespace: str | None = None
    fields: list[ParsedField]
