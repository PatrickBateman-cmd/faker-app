from fastapi import APIRouter, HTTPException

from app.schemas.balance import BalanceDeriveRequest
from app.services import balance_service

router = APIRouter(prefix="/datasets", tags=["balance"])


@router.post("/{dataset_id}/balances")
async def derive_balances(dataset_id: str, body: BalanceDeriveRequest):
    try:
        return balance_service.derive_balances(dataset_id, body)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
