from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["Service"])


class ServiceInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    status: str
    mcp_endpoint: str = Field(alias="mcpEndpoint")
    documentation_url: str = Field(alias="documentationUrl")
    health_url: str = Field(alias="healthUrl")


def _service_info() -> ServiceInfo:
    return ServiceInfo(
        name="DTU Course MCP Server",
        status="ok",
        mcpEndpoint="/mcp",
        documentationUrl="/docs",
        healthUrl="/health",
    )


@router.get("/", response_model=ServiceInfo, response_model_by_alias=True)
def homepage() -> ServiceInfo:
    return _service_info()


@router.get("/api/info", response_model=ServiceInfo, response_model_by_alias=True)
def service_info() -> ServiceInfo:
    return _service_info()
