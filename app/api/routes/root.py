from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["Service"])
INDEX_HTML = Path(__file__).resolve().parents[2] / "web" / "index.html"


class ServiceInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    status: str
    documentation_url: str = Field(alias="documentationUrl")
    health_url: str = Field(alias="healthUrl")


@router.get("/", include_in_schema=False, response_class=FileResponse)
def homepage() -> FileResponse:
    return FileResponse(INDEX_HTML)


@router.get("/api/info", response_model=ServiceInfo, response_model_by_alias=True)
def service_info() -> ServiceInfo:
    return ServiceInfo(
        name="DTU Course API",
        status="ok",
        documentationUrl="/docs",
        healthUrl="/health",
    )
