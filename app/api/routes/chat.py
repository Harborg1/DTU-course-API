from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.schemas.recommendation import ChatRequest, ChatResponse
from app.services.language_service import detect_user_language
from app.services.recommendation_service import recommend_courses

router = APIRouter(prefix="/api", tags=["Recommendations"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    response_model_by_alias=True,
    summary="Recommend official DTU courses and study programmes from student context",
)
def chat(request: ChatRequest, session: Annotated[Session, Depends(get_db)]) -> ChatResponse:
    user_messages = [message.content for message in request.messages if message.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=422, detail="At least one user message is required")
    academic_year = request.academic_year or get_settings().default_academic_year
    response = recommend_courses(session, messages=user_messages, academic_year=academic_year)
    response.response_language = detect_user_language(user_messages[-1])
    return response
