from pydantic import BaseModel, ConfigDict

from app.schemas.course import CourseSummary


class CourseSearchResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    count: int
    limit: int
    offset: int
    courses: list[CourseSummary]


class CourseListResponse(CourseSearchResponse):
    pass

