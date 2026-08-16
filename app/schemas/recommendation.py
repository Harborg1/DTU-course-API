from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=800)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=12)
    academic_year: str | None = Field(default=None, pattern=r"^\d{4}-\d{4}$", alias="academicYear")

    model_config = ConfigDict(populate_by_name=True)


class UnderstoodContext(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    topic: str
    level: str | None = None
    ects: float | None = None
    language: str | None = None
    period: str | None = None


class RecommendedCourse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    course_number: str = Field(alias="courseNumber")
    title: str
    ects: float | None = None
    level: str | None = None
    period: str | None = None
    schedule: str | None = None
    language: str | None = None
    department: str | None = None
    description: str | None = None
    reason: str
    source_url: str = Field(alias="sourceUrl")


class ChatResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reply: str
    understood: UnderstoodContext
    recommendations: list[RecommendedCourse]
    academic_year: str = Field(alias="academicYear")

