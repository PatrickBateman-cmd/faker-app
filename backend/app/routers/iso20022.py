from fastapi import APIRouter, HTTPException, Query

from app.services import iso20022_service

router = APIRouter(prefix="/iso20022", tags=["iso20022"])


@router.get("/domains")
async def list_domains():
    return iso20022_service.get_domains()


@router.get("/messages")
async def list_messages(
    domain: str | None = Query(None),
    page: int | None = Query(None, ge=0),
):
    if page is not None:
        return iso20022_service.get_messages(domain_id=domain, page=page)
    return iso20022_service.get_all_messages(domain_id=domain)


@router.get("/search")
async def search_messages(q: str = Query(..., min_length=2)):
    results = iso20022_service.search_messages(q)
    if not results:
        raise HTTPException(status_code=404, detail="No matching messages found")
    return results


@router.get("/messages/{message_id}")
async def get_message(message_id: str):
    msg = iso20022_service.get_message_by_id(message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return msg


@router.get("/messages/{message_id}/xsd")
async def parse_xsd(message_id: str):
    try:
        return iso20022_service.parse_xsd_for_message(message_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"XSD fetch/parse failed: {e!s}") from e


@router.post("/messages/{message_id}/generate")
async def generate_from_xsd(message_id: str):
    try:
        return iso20022_service.generate_from_xsd(message_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Generation failed: {e!s}") from e
