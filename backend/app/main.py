from contextlib import asynccontextmanager
from logging import getLogger

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.database import DuckDBManager
from app.routers import aggregation, datasets, exports, financial, generation, health, iso20022, kaggle, templates
from app.services import iso20022_service
from app.services.template_library import _init_sample_templates

logger = getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    DuckDBManager.initialize(db_path=settings.duckdb_path)
    _init_sample_templates()
    yield
    iso20022_service.close_client()
    DuckDBManager.close_instance()


app = FastAPI(
    title="Faker App",
    version="0.1.0",
    lifespan=lifespan,
)

_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)

app.include_router(health.router, prefix="")
app.include_router(templates.router, prefix="")
app.include_router(iso20022.router, prefix="")
app.include_router(generation.router, prefix="")
app.include_router(datasets.router, prefix="")
app.include_router(aggregation.router, prefix="")
app.include_router(exports.router, prefix="")
app.include_router(financial.router, prefix="")
app.include_router(kaggle.router, prefix="")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
