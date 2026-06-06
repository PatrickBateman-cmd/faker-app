import typer

from app.services.iso20022_service import (
    get_domains,
    get_message_by_id,
    get_messages,
    parse_xsd_for_message,
    search_messages,
)

from cli.common import console, output_result

app = typer.Typer(help="ISO 20022 catalog", no_args_is_help=True)


@app.command(name="domains")
def domains(
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
) -> None:
    """List ISO 20022 business domains."""
    doms = get_domains()
    rows = [[d.id, d.name] for d in doms]
    output_result(
        "ISO 20022 Domains",
        ["ID", "Name"],
        rows,
        fmt,
        json_data=[d.model_dump() for d in doms],
    )


@app.command(name="messages")
def list_messages(
    domain_id: str = typer.Argument(None, help="Domain ID (optional)"),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
) -> None:
    """List ISO 20022 messages (optionally filtered by domain)."""
    msgs = get_messages(domain_id=domain_id) if domain_id else get_messages()
    rows = [
        [m.message_id, m.message_name[:50], m.submitting_org, m.business_area]
        for m in msgs
    ]
    output_result(
        "Messages",
        ["ID", "Name", "Org", "Domain"],
        rows,
        fmt,
        json_data=[m.model_dump() for m in msgs],
    )


@app.command(name="search")
def search(
    query: str = typer.Argument(..., help="Search query"),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
) -> None:
    """Search ISO 20022 messages by ID or name."""
    results = search_messages(query)
    if not results:
        console.print("[yellow]No matching messages found.[/yellow]")
        return
    rows = [
        [m.message_id, m.message_name[:60], m.submitting_org, m.business_area]
        for m in results
    ]
    output_result(
        f"Search: '{query}' ({len(results)} results)",
        ["ID", "Name", "Org", "Domain"],
        rows,
        fmt,
        json_data=[m.model_dump() for m in results],
    )


@app.command(name="xsd")
def xsd(
    message_id: str = typer.Argument(..., help="Message ID (e.g. pacs.008.001.12)"),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
) -> None:
    """Fetch and show XSD-parsed fields for a message."""
    with console.status(f"Fetching XSD for {message_id}..."):
        parsed = parse_xsd_for_message(message_id)

    if not parsed.fields:
        console.print(f"[yellow]No fields found for '{message_id}'[/yellow]")
        return

    rows = [
        [
            f.name,
            f.xsd_type,
            f.mapped_generator,
            str(f.min_occurs),
            f.max_occurs,
            ", ".join(f.enumeration_values[:5]) + ("..." if f.enumeration_values and len(f.enumeration_values) > 5 else "") if f.enumeration_values else "",
            f.documentation or "",
        ]
        for f in parsed.fields
    ]

    output_result(
        f"{parsed.message_name} — Fields ({len(parsed.fields)})",
        ["Name", "XSD Type", "Generator", "Min", "Max", "Enum", "Doc"],
        rows,
        fmt,
        json_data=parsed.model_dump(),
    )


@app.command(name="save-template")
def save_template(
    message_id: str = typer.Argument(..., help="Message ID (e.g. pacs.008.001.12)"),
    name: str = typer.Option(None, "--name", "-n", help="Custom template name"),
    fmt: str = typer.Option("table", "--format", "-f", help="Output format"),
) -> None:
    """Save an ISO 20022 message as a template."""
    from app.services.template_library import create_template

    msg = get_message_by_id(message_id)
    msg_name = msg.message_name if msg else message_id

    with console.status(f"Fetching XSD for {message_id}..."):
        parsed = parse_xsd_for_message(message_id)

    fields_xml_parts = []
    for f in parsed.fields:
        attrs = f'name="{f.name}" type="{_xsd_to_field_type(f.xsd_type)}" generator="{f.mapped_generator}"'
        constraint_parts = []
        if f.enumeration_values:
            constraint_parts.append(f'values="{",".join(f.enumeration_values)}"')
        if constraint_parts:
            attrs += f" constraint=\"{' '.join(constraint_parts)}\""
        fields_xml_parts.append(f"    <field {attrs}/>")

    fields_xml = "\n".join(fields_xml_parts)
    tpl_name = name or f"{message_id} - {msg_name}"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<template name="{tpl_name}" category="ISO 20022">
  <meta description="ISO 20022 {message_id} — {msg_name}" version="1.0"/>
{fields_xml}
</template>"""

    try:
        tpl = create_template(xml)
    except ValueError as e:
        if "already exists" in str(e):
            console.print(f"[yellow]Template '{tpl_name}' already exists (HTTP 409)[/yellow]")
            raise typer.Exit(code=1) from e
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e

    rows = [[tpl.name, tpl.category, tpl.meta.description, str(len(tpl.fields))]]
    output_result(
        "Template Saved",
        ["Name", "Category", "Description", "Fields"],
        rows,
        fmt,
        json_data=tpl.model_dump(),
    )
    console.print(f"\n[green]Use:[/green] faker generate --name data --rows 100 --template \"{tpl_name}\"")


def _xsd_to_field_type(xsd_type: str) -> str:
    base = xsd_type.split("}")[-1] if "}" in xsd_type else xsd_type
    base_lower = base.lower()
    if "decimal" in base_lower:
        return "float"
    if "integer" in base_lower or "int" in base_lower:
        return "integer"
    if "date" in base_lower:
        return "date"
    if "boolean" in base_lower:
        return "boolean"
    if "time" in base_lower:
        return "datetime"
    return "string"
