from __future__ import annotations

import json
import random
import re
import time
from datetime import datetime
from logging import getLogger
from urllib.parse import urlparse, urljoin

import httpx
from lxml import etree, html

from app.core.database import DuckDBManager
from app.schemas.iso20022 import DomainInfo, MessageInfo, ParsedField, XsdParsedResponse

logger = getLogger(__name__)

_CACHE_TTL_SECONDS = 3600

CATALOG_BASE = "https://www.iso20022.org"
CATALOG_URL = f"{CATALOG_BASE}/iso-20022-message-definitions"

_HTTP_CLIENT: httpx.Client | None = None

_ALLOWED_XSD_HOSTS = {"www.iso20022.org", "iso20022.org"}


def _get_client() -> httpx.Client:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        _HTTP_CLIENT = httpx.Client(
            timeout=10, follow_redirects=True,
            headers={"User-Agent": "FakerApp/0.1"},
        )
    return _HTTP_CLIENT


def close_client() -> None:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is not None:
        _HTTP_CLIENT.close()
        _HTTP_CLIENT = None

NSMAP = {
    "xs": "http://www.w3.org/2001/XMLSchema",
}

FIELD_MAPPINGS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)\b(amount|value|price|total|sum|limit|fee|tax|charge|rate|interest|payment_amount|sttlm_amt|instd_amt|reqd_advd_amt|ccy_amt)\b"), "pydecimal"),
    (re.compile(r"(?i)\b(currency|ccy)\b"), "currency_code"),
    (re.compile(r"(?i)\b(bic|swift)\b"), "swift"),
    (re.compile(r"(?i)\b(iban)\b"), "iban"),
    (re.compile(r"(?i)\b(bban)\b"), "bban"),
    (re.compile(r"(?i)\b(email|electronic_mail)\b"), "email"),
    (re.compile(r"(?i)\b(phone|telephone|contact|mobile|fax)\b"), "phone_number"),
    (re.compile(r"(?i)\b(country|ctry|nation|cntry)\b"), "country_code"),
    (re.compile(r"(?i)\b(city|town|municipality)\b"), "city"),
    (re.compile(r"(?i)\b(postal_code|zip|post_code|pstl_cd)\b"), "zipcode"),
    (re.compile(r"(?i)\b(address|street|adr|line|pstl_adr)\b"), "street_address"),
    (re.compile(r"(?i)\b(name|nm|full_name|surname|last_name|first_name|gvn_nm|faml_nm|middl_nm)\b"), "name"),
    (re.compile(r"(?i)\b(date|dt|timestamp|datetime|cre_dt|due_date|reqd_exctn_dt|intnd_to_dt)\b"), "date_between"),
    (re.compile(r"(?i)\b(uri|url|link|website|web)\b"), "url"),
    (re.compile(r"(?i)\b(description|desc|purpose|purp|note|rmk|instr|addtl_inf)\b"), "text"),
    (re.compile(r"(?i)\b(id|identifier|ref|reference|acct_id|tx_id|msg_id|msg_rcpt|end_to_end_id|uetr|clr_sys_ref)\b"), "bothify"),
    (re.compile(r"(?i)\b(account|acct|acct_id)\b"), "bban"),
    (re.compile(r"(?i)\b(bank|financial_institution|instg_agt|instd_agt|agt)\b"), "company"),
    (re.compile(r"(?i)\b(status|stat|sts)\b"), "random_element"),
    (re.compile(r"(?i)\b(type|tp|kind|categ|ctgy)\b"), "random_element"),
    (re.compile(r"(?i)\b(code|cd)\b"), "bothify"),
    (re.compile(r"(?i)\b(percent|pctg|pct)\b"), "pydecimal"),
    (re.compile(r"(?i)\b(quantity|qty|count|nb|number|nmbr|total_qty)\b"), "random_int"),
    (re.compile(r"(?i)\b(boolean|flag|indicator|ind|active|enabled|yes_no|authntcn_ind)\b"), "boolean"),
    (re.compile(r"(?i)\b(credit|debit|cdt|dbt|charge)\b"), "random_element"),
    (re.compile(r"(?i)\b(exchange|xchg_rate|rate|fx_rate)\b"), "pydecimal"),
    (re.compile(r"(?i)\b(sequence|seq|order|ordr)\b"), "random_int"),
    (re.compile(r"(?i)\b(version|vrsn)\b"), "random_int"),
]


def _map_field_type(field_name: str, xsd_type: str | None, enumeration: list[str] | None) -> str:
    if enumeration:
        return "random_element"

    if xsd_type:
        base = xsd_type.split("}")[-1] if "}" in xsd_type else xsd_type
        base_lower = base.lower()
        if "decimal" in base_lower:
            return "pydecimal"
        if "integer" in base_lower or "int" in base_lower:
            return "random_int"
        if "date" in base_lower:
            return "date_between"
        if "boolean" in base_lower:
            return "boolean"
        if "time" in base_lower:
            return "date_time"

    for pattern, generator in FIELD_MAPPINGS:
        if pattern.search(field_name):
            return generator

    if xsd_type and "decimal" in xsd_type.lower():
        return "pydecimal"

    logger.warning("Unrecognized field type (xsd=%s, name=%s), falling back to 'text'", xsd_type, field_name)
    return "text"


XML_NS_RE = re.compile(r"\{[^}]+\}")


def _strip_ns(tag: str) -> str:
    return XML_NS_RE.sub("", tag)


def _fetch_page(url: str) -> str:
    client = _get_client()
    resp = client.get(url)
    resp.raise_for_status()
    return resp.text


def _cache_get(key: str) -> str | None:
    db = DuckDBManager.get_instance()
    row = db.execute(
        "SELECT data_json, fetched_at FROM metadata_iso_cache WHERE cache_key = ?",
        [key],
    ).fetchone()
    if not row:
        return None
    data_json, fetched_at = row
    age = (datetime.now() - fetched_at).total_seconds() if fetched_at else _CACHE_TTL_SECONDS + 1
    if age > _CACHE_TTL_SECONDS:
        return None
    return data_json


def _cache_set(key: str, data: object) -> None:
    db = DuckDBManager.get_instance()
    db.execute(
        "INSERT OR REPLACE INTO metadata_iso_cache (cache_key, data_json, fetched_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
        [key, json.dumps(data)],
    )


def _fetch_xsd(url: str) -> str:
    full_url = url if url.startswith("http") else urljoin(CATALOG_BASE, url)
    parsed = urlparse(full_url)
    if parsed.netloc not in _ALLOWED_XSD_HOSTS:
        raise ValueError(f"Refusing to fetch XSD from off-host URL: {full_url}")
    return _fetch_page(full_url)


def get_domains() -> list[DomainInfo]:
    cached = _cache_get("domains")
    if cached:
        return [DomainInfo(**d) for d in json.loads(cached)]
    try:
        raw = _fetch_page(CATALOG_URL)
    except httpx.TimeoutException:
        return _default_domains()
    except httpx.HTTPError:
        return _default_domains()

    tree = html.fromstring(raw)

    domains: list[DomainInfo] = []
    seen = set()
    for link in tree.xpath("//a[contains(@href, 'business-domain')]"):
        href = link.get("href", "")
        name = link.text_content().strip()
        if name and name not in seen and href:
            seen.add(name)
            m = re.search(r"business-domain%5B0%5D=(\d+)", href)
            if m:
                domains.append(DomainInfo(id=m.group(1), name=name))
    result = domains if domains else _default_domains()
    _cache_set("domains", [d.model_dump() for d in result])
    return result


def _default_domains() -> list[DomainInfo]:
    return [
        DomainInfo(id="1", name="Payments"),
        DomainInfo(id="6", name="Securities"),
        DomainInfo(id="11", name="Trade Finance"),
        DomainInfo(id="16", name="Cards"),
        DomainInfo(id="21", name="FX"),
    ]


def get_messages(domain_id: str | None = None, page: int = 0) -> list[MessageInfo]:
    cache_key = f"messages:{domain_id or ''}:{page}"
    cached = _cache_get(cache_key)
    if cached:
        return [MessageInfo(**m) for m in json.loads(cached)]

    params = f"?page={page}"
    if domain_id:
        params = f"?business-domain%5B0%5D={domain_id}&page={page}"
    url = CATALOG_URL + params
    try:
        raw = _fetch_page(url)
    except (httpx.TimeoutException, httpx.HTTPError):
        return _default_messages(domain_id)
    tree = html.fromstring(raw)

    messages: list[MessageInfo] = []
    business_area = ""

    ba_elem = tree.xpath("//div[contains(@class, 'business-area')]//a")
    if ba_elem:
        business_area = ba_elem[0].text_content().strip()

    sections = tree.xpath("//details | //div[contains(@class, 'views-row')]")
    if not sections:
        result = _parse_message_table_fallback(tree, domain_id)
        _cache_set(cache_key, [m.model_dump() for m in result])
        return result

    for section in sections:
        title_el = section.xpath(".//summary | .//h3 | .//h4")
        for el in section.xpath(".//tr | .//div[contains(@class, 'views-row')]"):
            cells = el.xpath(".//td | .//span[contains(@class, 'views-field')]")
            if len(cells) < 3:
                continue
            msg_id = cells[0].text_content().strip()
            msg_name = cells[1].text_content().strip() if len(cells) > 1 else ""
            org = cells[2].text_content().strip() if len(cells) > 2 else ""
            xsd_link = ""
            for cell in cells:
                a = cell.xpath(".//a[contains(@href, '/message/') and contains(@href, '/download')]")
                if a:
                    xsd_link = a[0].get("href", "")
                    break

            if msg_id and re.match(r"^[a-z]+\.[0-9]{3}\.[0-9]{3}\.[0-9]{2,3}$", msg_id):
                messages.append(
                    MessageInfo(
                        message_id=msg_id,
                        message_name=msg_name,
                        submitting_org=org,
                        business_area=business_area,
                        xsd_url=xsd_link if xsd_link else None,
                    )
                )

    _cache_set(cache_key, [m.model_dump() for m in messages])
    return messages


def get_all_messages(domain_id: str | None = None) -> list[MessageInfo]:
    all_msgs: list[MessageInfo] = []
    page = 0
    while True:
        msgs = get_messages(domain_id=domain_id, page=page)
        if not msgs:
            break
        if msgs == _default_messages(domain_id):
            return msgs
        if page > 0 and set((m.message_id, m.message_name) for m in msgs) <= set(
            (m.message_id, m.message_name) for m in all_msgs
        ):
            break
        all_msgs.extend(msgs)
        page += 1
    return all_msgs


def _parse_message_table_fallback(tree, domain_id=None):
    messages: list[MessageInfo] = []
    rows = tree.xpath("//table//tr")
    for row in rows:
        cells = row.xpath(".//td")
        if len(cells) < 3:
            continue
        msg_id = cells[0].text_content().strip()
        msg_name = cells[1].text_content().strip() if len(cells) > 1 else ""
        org = cells[2].text_content().strip() if len(cells) > 2 else ""
        xsd_url = ""
        for cell in cells:
            a = cell.xpath(".//a[contains(@href, '/message/') and contains(@href, '/download')]")
            if a:
                xsd_url = a[0].get("href", "")
                break
        if msg_id and re.match(r"^[a-z]+\.[0-9]{3}\.[0-9]{3}\.[0-9]{2,3}$", msg_id):
            messages.append(
                MessageInfo(
                    message_id=msg_id,
                    message_name=msg_name,
                    submitting_org=org,
                    business_area="",
                    xsd_url=xsd_url if xsd_url else None,
                )
            )
    return messages


def _default_messages(domain_id: str | None = None) -> list[MessageInfo]:
    samples = [
        MessageInfo(message_id="pacs.008.001.12", message_name="FIToFICustomerCreditTransfer", submitting_org="SWIFT", business_area="Payments", xsd_url=None),
        MessageInfo(message_id="pacs.009.001.12", message_name="FinancialInstitutionCreditTransfer", submitting_org="SWIFT", business_area="Payments", xsd_url=None),
        MessageInfo(message_id="pacs.004.001.12", message_name="PaymentReturn", submitting_org="SWIFT", business_area="Payments", xsd_url=None),
        MessageInfo(message_id="pain.001.001.12", message_name="CustomerCreditTransferInitiation", submitting_org="SWIFT", business_area="Payments", xsd_url=None),
        MessageInfo(message_id="pain.002.001.13", message_name="CustomerPaymentStatusReport", submitting_org="SWIFT", business_area="Payments", xsd_url=None),
        MessageInfo(message_id="camt.053.001.12", message_name="BankToCustomerStatement", submitting_org="SWIFT", business_area="Payments", xsd_url=None),
        MessageInfo(message_id="camt.054.001.12", message_name="BankToCustomerDebitCreditNotification", submitting_org="SWIFT", business_area="Payments", xsd_url=None),
        MessageInfo(message_id="camt.056.001.11", message_name="FIToFIPaymentCancellationRequest", submitting_org="SWIFT", business_area="Payments", xsd_url=None),
        MessageInfo(message_id="seev.031.001.14", message_name="CorporateActionInstruction", submitting_org="SWIFT", business_area="Securities", xsd_url=None),
        MessageInfo(message_id="seev.002.001.14", message_name="CorporateActionMovementConfirmation", submitting_org="SWIFT", business_area="Securities", xsd_url=None),
        MessageInfo(message_id="setr.002.001.09", message_name="OrderConfirmation", submitting_org="SWIFT", business_area="Securities", xsd_url=None),
        MessageInfo(message_id="fxtr.010.001.03", message_name="TradeConfirmation", submitting_org="SWIFT", business_area="FX", xsd_url=None),
    ]
    if domain_id:
        domain_map = {"1": "Payments", "6": "Securities", "11": "Trade Finance", "16": "Cards", "21": "FX"}
        domain_name = domain_map.get(domain_id, "")
        return [m for m in samples if m.business_area == domain_name]
    return samples


def get_message_by_id(message_id: str) -> MessageInfo | None:
    for m in _default_messages():
        if m.message_id == message_id:
            return m
    try:
        for page in range(2):
            messages = get_messages(page=page)
            for m in messages:
                if m.message_id == message_id:
                    return m
    except (httpx.TimeoutException, httpx.HTTPError):
        pass
    return None


def search_messages(q: str) -> list[MessageInfo]:
    q_lower = q.lower()
    seen: set[str] = set()
    results: list[MessageInfo] = []

    def match_and_add(msg: MessageInfo) -> None:
        if msg.message_id not in seen and (
            q_lower in msg.message_id.lower() or q_lower in msg.message_name.lower()
        ):
            results.append(msg)
            seen.add(msg.message_id)

    for m in _default_messages():
        match_and_add(m)

    results.sort(key=lambda m: (m.business_area, m.message_id))
    return results


_SECURE_XSD_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)


def _parse_xsd_fields(xsd_content: str, message_id: str, message_name: str) -> XsdParsedResponse:
    try:
        root = etree.fromstring(xsd_content.encode(), _SECURE_XSD_PARSER)
    except etree.XMLSyntaxError:
        return XsdParsedResponse(message_id=message_id, message_name=message_name, fields=[])

    ns = root.nsmap.get(None, "http://www.w3.org/2001/XMLSchema")
    nsmap = {"xs": ns}

    fields: list[ParsedField] = []
    seen = set()

    elements = root.xpath("//xs:element", namespaces=nsmap)
    if not elements:
        elements = root.xpath("//*[local-name()='element']")

    for elem in elements[:50]:
        name = elem.get("name", "")
        if not name or name == "Document" or name in seen:
            continue
        seen.add(name)

        ref = elem.get("ref", "")
        type_attr = elem.get("type", "")
        min_o = int(elem.get("minOccurs", "1"))
        max_o = elem.get("maxOccurs", "1")

        doc = ""
        annotation = elem.xpath("xs:annotation/xs:documentation", namespaces=nsmap)
        if annotation:
            doc = " ".join(annotation[0].text_content().split())

        enum_values: list[str] | None = None
        resolved_type = type_attr or ref

        if type_attr:
            enum_values = _extract_enum_from_type(root, type_attr, nsmap)
        if ref:
            enum_values = _extract_enum_from_element(root, ref, nsmap)

        if not enum_values:
            enum_values = _extract_enum_inline(elem, nsmap)

        generator = _map_field_type(name, resolved_type, enum_values)
        if enum_values and generator != "random_element":
            generator = "random_element"

        nested = _parse_nested_fields(elem, root, nsmap)

        field = ParsedField(
            name=name,
            xsd_type=resolved_type or "",
            mapped_generator=generator,
            min_occurs=min_o,
            max_occurs=str(max_o),
            documentation=doc or None,
            enumeration_values=enum_values,
            nested_fields=nested if nested else None,
        )
        fields.append(field)

    return XsdParsedResponse(
        message_id=message_id,
        message_name=message_name,
        namespace=ns,
        fields=fields,
    )


def _extract_enum_from_type(root: etree._Element, type_name: str, nsmap: dict) -> list[str] | None:
    parts = type_name.split(":")
    local_name = parts[-1]
    prefix = parts[0] if len(parts) > 1 else "xs"
    tns = nsmap.get(prefix, nsmap.get("xs", "http://www.w3.org/2001/XMLSchema"))

    type_def = root.xpath(
        f"//xs:simpleType[@name='{local_name}']/xs:restriction/xs:enumeration",
        namespaces=nsmap,
    )
    if not type_def:
        type_def = root.xpath(
            f"//*[local-name()='simpleType' and @name='{local_name}']//*[local-name()='enumeration']"
        )
    if type_def:
        return [e.get("value", "") for e in type_def if e.get("value")]
    return None


def _extract_enum_from_element(root: etree._Element, ref_name: str, nsmap: dict) -> list[str] | None:
    parts = ref_name.split(":")
    local_name = parts[-1]
    elem_def = root.xpath(f"//xs:element[@name='{local_name}']", namespaces=nsmap)
    if not elem_def:
        elem_def = root.xpath(f"//*[local-name()='element' and @name='{local_name}']")
    if elem_def:
        return _extract_enum_inline(elem_def[0], nsmap)
    return None


def _extract_enum_inline(elem: etree._Element, nsmap: dict) -> list[str] | None:
    enums = elem.xpath(
        ".//xs:restriction/xs:enumeration",
        namespaces=nsmap,
    )
    if not enums:
        enums = elem.xpath(
            ".//*[local-name()='restriction']/*[local-name()='enumeration']"
        )
    if enums:
        vals = [e.get("value", "") for e in enums if e.get("value")]
        return vals if vals else None
    return None


def _parse_nested_fields(elem: etree._Element, root: etree._Element, nsmap: dict) -> list[ParsedField] | None:
    children = elem.xpath(
        ".//xs:complexType//xs:sequence//xs:element",
        namespaces=nsmap,
    )
    if not children:
        children = elem.xpath(
            ".//*[local-name()='complexType']//*[local-name()='sequence']//*[local-name()='element']"
        )
    if not children:
        return None

    nested: list[ParsedField] = []
    for child in children[:10]:
        cname = child.get("name", "")
        if not cname:
            continue
        ctype = child.get("type", "")
        gen = _map_field_type(cname, ctype, None)
        nested.append(
            ParsedField(
                name=cname,
                xsd_type=ctype,
                mapped_generator=gen,
                min_occurs=int(child.get("minOccurs", "1")),
                max_occurs=child.get("maxOccurs", "1"),
            )
        )
    return nested if nested else None


def parse_xsd_for_message(message_id: str) -> XsdParsedResponse:
    cached = _cache_get(f"xsd:{message_id}")
    if cached:
        return XsdParsedResponse(**json.loads(cached))

    msg = get_message_by_id(message_id)
    message_name = msg.message_name if msg else message_id
    xsd_url = msg.xsd_url if msg and msg.xsd_url else ""

    if not xsd_url:
        result = XsdParsedResponse(
            message_id=message_id,
            message_name=message_name,
            fields=_generate_demo_fields(),
        )
        _cache_set(f"xsd:{message_id}", result.model_dump())
        return result

    try:
        xsd_content = _fetch_xsd(xsd_url)
    except (httpx.TimeoutException, httpx.HTTPError):
        result = XsdParsedResponse(
            message_id=message_id,
            message_name=message_name,
            fields=_generate_demo_fields(),
        )
        _cache_set(f"xsd:{message_id}", result.model_dump())
        return result

    try:
        result = _parse_xsd_fields(xsd_content, message_id, message_name)
    except etree.XMLSyntaxError:
        result = XsdParsedResponse(
            message_id=message_id,
            message_name=message_name,
            fields=_generate_demo_fields(),
        )
        _cache_set(f"xsd:{message_id}", result.model_dump())
        return result

    if not result.fields:
        result = XsdParsedResponse(
            message_id=message_id,
            message_name=message_name,
            fields=_generate_demo_fields(),
        )

    _cache_set(f"xsd:{message_id}", result.model_dump())
    return result


def _generate_demo_fields() -> list[ParsedField]:
    return [
        ParsedField(name="MessageId", xsd_type="Max35Text", mapped_generator="bothify", min_occurs=1, max_occurs="1", documentation="Unique message identifier", enumeration_values=None),
        ParsedField(name="CreationDateTime", xsd_type="ISODateTime", mapped_generator="date_time", min_occurs=1, max_occurs="1", documentation="Date and time of message creation"),
        ParsedField(name="NumberOfTransactions", xsd_type="Max15NumericText", mapped_generator="random_int", min_occurs=1, max_occurs="1"),
        ParsedField(name="TotalAmount", xsd_type="DecimalNumber", mapped_generator="pydecimal", min_occurs=1, max_occurs="1", documentation="Total transaction amount"),
        ParsedField(name="Currency", xsd_type="ActiveCurrencyCode", mapped_generator="currency_code", min_occurs=1, max_occurs="1", enumeration_values=["EUR", "USD", "GBP", "CHF", "JPY"]),
        ParsedField(name="Status", xsd_type="TransactionStatus", mapped_generator="random_element", min_occurs=1, max_occurs="1", enumeration_values=["ACCC", "ACSP", "ACSC", "ACCP", "RJCT", "PDNG"]),
        ParsedField(name="DebtorName", xsd_type="Max140Text", mapped_generator="name", min_occurs=1, max_occurs="1"),
        ParsedField(name="DebtorIBAN", xsd_type="IBAN2007Identifier", mapped_generator="iban", min_occurs=1, max_occurs="1"),
        ParsedField(name="CreditorName", xsd_type="Max140Text", mapped_generator="name", min_occurs=1, max_occurs="1"),
        ParsedField(name="CreditorIBAN", xsd_type="IBAN2007Identifier", mapped_generator="iban", min_occurs=1, max_occurs="1"),
        ParsedField(name="BIC", xsd_type="BICIdentifier", mapped_generator="swift", min_occurs=1, max_occurs="1"),
        ParsedField(name="ChargeBearer", xsd_type="ChargeBearerType1Code", mapped_generator="random_element", min_occurs=1, max_occurs="1", enumeration_values=["DEBT", "CRED", "SHAR", "SLEV"]),
        ParsedField(name="Purpose", xsd_type="Max140Text", mapped_generator="random_element", min_occurs=0, max_occurs="1", enumeration_values=["SALA", "SUPP", "TAXS", "INTC", "TRAD", "CONS", "GOVT"]),
        ParsedField(name="RemittanceInfo", xsd_type="Max140Text", mapped_generator="text", min_occurs=0, max_occurs="1", documentation="Unstructured remittance information"),
        ParsedField(name="Country", xsd_type="CountryCode", mapped_generator="country_code", min_occurs=1, max_occurs="1", enumeration_values=["DE", "FR", "GB", "IT", "ES", "NL", "BE", "AT", "CH"]),
    ]


def generate_from_xsd(message_id: str) -> list[dict]:
    parsed = parse_xsd_for_message(message_id)
    rows = []
    for _ in range(10):
        row = {}
        for field in parsed.fields:
            row[field.name] = _generate_value(field)
        rows.append(row)
    return rows


def _generate_value(field: ParsedField) -> str:
    gen = field.mapped_generator
    if gen == "random_element" and field.enumeration_values:
        return random.choice(field.enumeration_values)
    if gen == "pydecimal":
        return str(round(random.uniform(0.01, 999999.99), 2))
    if gen == "random_int":
        return str(random.randint(0, 999999))
    if gen == "boolean":
        return random.choice(["true", "false"])
    if gen == "currency_code":
        return random.choice(["EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD", "SEK", "NOK", "DKK", "PLN", "CZK"])
    if gen == "country_code":
        return random.choice(["DE", "FR", "GB", "IT", "ES", "NL", "BE", "AT", "CH", "PL", "SE", "NO", "DK", "FI", "PT"])
    if gen == "name":
        return random.choice(["John Smith", "Maria Garcia", "Hans Mueller", "Sophie Dubois", "Luca Rossi", "Anna Kowalski"])
    if gen == "company":
        return random.choice(["Acme Corp", "Global Finance Ltd", "EuroBank SA", "Nordic Trade AB", "Mediterranean Shipping"])
    if gen == "swift":
        return "BOFAUS3NXXX"
    if gen == "iban":
        return f"DE{random.randint(10,99)}100{random.randint(1000000000,9999999999)}"
    if gen == "bban":
        return f"{random.randint(10000000,99999999)}"
    if gen == "bothify":
        return f"REF-{int(time.time()) % 100000}"
    if gen == "date_between":
        return "2024-06-01"
    if gen == "date_time":
        return "2024-06-01T10:30:00"
    if gen == "text":
        return "Sample text value"
    if gen == "url":
        return "https://example.com"
    if gen == "city":
        return "Berlin"
    if gen == "zipcode":
        return "10115"
    if gen == "street_address":
        return "123 Main Street"
    if gen == "phone_number":
        return "+49 30 12345678"
    if gen == "email":
        return "user@example.com"
    return f"[{gen}]"
