from fastapi import APIRouter, HTTPException, Query

from app.services import dataset_service

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("")
async def list_datasets():
    return dataset_service.list_datasets()


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: str):
    ds = dataset_service.get_dataset(dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds


@router.get("/{dataset_id}/rows")
async def get_dataset_rows(
    dataset_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=1000),
):
    result = dataset_service.get_dataset_rows(dataset_id, page=page, per_page=per_page)
    if result["meta"] is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return result


@router.get("/{dataset_id}/columns")
async def get_dataset_columns(dataset_id: str):
    cols = dataset_service.get_dataset_columns(dataset_id)
    if not cols:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return cols


@router.delete("/{dataset_id}", status_code=204)
async def delete_dataset(dataset_id: str):
    deleted = dataset_service.delete_dataset(dataset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset not found")
