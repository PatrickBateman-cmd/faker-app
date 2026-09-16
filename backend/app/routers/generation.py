from fastapi import APIRouter, HTTPException, Query

from app.schemas.generation import GenerateRequest
from app.services import generation_engine
from app.services.generation_engine.queries import DEFAULT_RECON_BREAKS_LIMIT, MAX_RECON_BREAKS_LIMIT

router = APIRouter(prefix="/generate", tags=["generation"])


@router.post("")
async def generate(body: GenerateRequest):
    try:
        return generation_engine.generate_datasets(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {e!s}") from e


@router.get("/runs/{run_id}/breaks")
async def get_breaks(
    run_id: int,
    limit: int = Query(DEFAULT_RECON_BREAKS_LIMIT, ge=1, le=MAX_RECON_BREAKS_LIMIT),
    offset: int = Query(0, ge=0),
):
    return generation_engine.get_recon_breaks(run_id, limit=limit, offset=offset)
