from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import template_library

router = APIRouter(prefix="/templates", tags=["templates"])


class CreateTemplateBody(BaseModel):
    xml_content: str


class UpdateTemplateBody(BaseModel):
    xml_content: str


@router.get("")
async def list_templates():
    return template_library.list_templates()


@router.get("/{name}")
async def get_template(name: str):
    t = template_library.get_template(name)
    if t is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@router.post("", status_code=201)
async def create_template(body: CreateTemplateBody):
    try:
        t = template_library.create_template(body.xml_content)
        return t
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.put("/{name}")
async def update_template(name: str, body: UpdateTemplateBody):
    try:
        t = template_library.update_template(name, body.xml_content)
        return t
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{name}", status_code=204)
async def delete_template(name: str):
    deleted = template_library.delete_template(name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
