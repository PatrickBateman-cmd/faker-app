from fastapi import APIRouter, HTTPException

from app.schemas.generation import GenerateRequest
from app.services import generation_engine

router = APIRouter(prefix="/generate", tags=["generation"])


@router.post("")
async def generate(body: GenerateRequest):
    try:
        return generation_engine.generate_datasets(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {e!s}") from e
