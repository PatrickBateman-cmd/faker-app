from fastapi import APIRouter, HTTPException

from app.schemas.aggregation import AggregateRequest, DedupRequest
from app.services import transform_service

router = APIRouter(prefix="/datasets", tags=["aggregation"])


@router.post("/{dataset_id}/aggregate")
async def aggregate_dataset(dataset_id: str, body: AggregateRequest):
    try:
        return transform_service.aggregate_dataset(dataset_id, body)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{dataset_id}/dedup")
async def dedup_dataset(dataset_id: str, body: DedupRequest):
    try:
        return transform_service.dedup_dataset(dataset_id, body)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
