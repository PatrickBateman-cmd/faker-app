from fastapi import APIRouter, HTTPException, Query

from app.schemas.kaggle import KaggleImportRequest, KaggleImportResponse
from app.services import kaggle_service

router = APIRouter(prefix="/kaggle", tags=["kaggle"])


@router.get("/credentials")
async def check_credentials():
    return {"configured": kaggle_service.credentials_configured()}


@router.get("/search")
async def search(
    q: str = Query(..., description="Search query"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    try:
        return kaggle_service.search_datasets(q, page=page, per_page=per_page)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/datasets/{owner}/{slug}/files")
async def list_files(owner: str, slug: str):
    try:
        return kaggle_service.list_files(owner, slug)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/import", response_model=KaggleImportResponse)
async def import_dataset(body: KaggleImportRequest) -> KaggleImportResponse:
    try:
        result = kaggle_service.import_file(
            owner=body.owner,
            slug=body.slug,
            file_name=body.file_name,
            dataset_name=body.dataset_name,
            max_rows=body.max_rows,
        )
        return KaggleImportResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
