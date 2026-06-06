from contextlib import asynccontextmanager
from logging import getLogger

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.database import DuckDBManager
from app.routers import aggregation, datasets, exports, financial, generation, health, iso20022, templates
from app.services.template_library import _init_sample_templates

logger = getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    DuckDBManager.initialize(db_path=settings.duckdb_path)
    _init_sample_templates()
    yield
    DuckDBManager.close_instance()


app = FastAPI(
    title="Faker App",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="")
app.include_router(templates.router, prefix="")
app.include_router(iso20022.router, prefix="")
app.include_router(generation.router, prefix="")
app.include_router(datasets.router, prefix="")
app.include_router(aggregation.router, prefix="")
app.include_router(exports.router, prefix="")
app.include_router(financial.router, prefix="")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
