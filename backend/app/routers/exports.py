import os

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from app.services import export_service

router = APIRouter(prefix="/datasets", tags=["exports"])


def _cleanup(filepath: str) -> None:
    try:
        if os.path.exists(filepath):
            os.unlink(filepath)
    except Exception:
        pass


@router.get("/{dataset_id}/export/csv")
async def export_csv(dataset_id: str, background_tasks: BackgroundTasks):
    try:
        filepath = export_service.export_csv(dataset_id)
        filename = os.path.basename(filepath)
        background_tasks.add_task(_cleanup, filepath)
        return FileResponse(filepath, media_type="text/csv", filename=filename)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{dataset_id}/export/parquet")
async def export_parquet(dataset_id: str, background_tasks: BackgroundTasks):
    try:
        filepath = export_service.export_parquet(dataset_id)
        filename = os.path.basename(filepath)
        background_tasks.add_task(_cleanup, filepath)
        return FileResponse(
            filepath, media_type="application/octet-stream", filename=filename
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{dataset_id}/export/xlsx")
async def export_xlsx(dataset_id: str, background_tasks: BackgroundTasks):
    try:
        filepath = export_service.export_xlsx(dataset_id)
        filename = os.path.basename(filepath)
        background_tasks.add_task(_cleanup, filepath)
        return FileResponse(
            filepath,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=filename,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{dataset_id}/export/jsonl")
async def export_jsonl(dataset_id: str, background_tasks: BackgroundTasks):
    try:
        filepath = export_service.export_jsonl(dataset_id)
        filename = os.path.basename(filepath)
        background_tasks.add_task(_cleanup, filepath)
        return FileResponse(
            filepath, media_type="application/x-ndjson", filename=filename
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
