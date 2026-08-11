from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    status: str
    database: str
    academic_year: str = Field(alias="academicYear")


@router.get("/health", response_model=HealthResponse, response_model_by_alias=True)
def health(session: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable") from exc
    return HealthResponse(status="ok", database="ok", academicYear=get_settings().default_academic_year)

