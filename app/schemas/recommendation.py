from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=800)


class UnderstoodContext(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    topic: str
    level: str | None = None
    ects: float | None = None
    language: str | None = None
    period: str | None = None
    program: str | None = None


TurnOperation = Literal[
    "course_search",
    "course_detail",
    "study_program_recommendation",
    "study_plan",
    "specialization",
    "comparison",
    "clarification",
    "general",
]
CourseResultMode = Literal["summary", "all"]


class CompletedTurnState(BaseModel):
    """Compact facts from a completed turn; previous prose is deliberately excluded."""

    model_config = ConfigDict(populate_by_name=True)

    status: Literal["completed"] = "completed"
    request: str = Field(min_length=1, max_length=800)
    operation: TurnOperation
    topic: str | None = Field(default=None, max_length=200)
    level: str | None = Field(default=None, max_length=100)
    ects: float | None = None
    language: str | None = Field(default=None, max_length=100)
    period: str | None = Field(default=None, max_length=100)
    result_mode: CourseResultMode | None = Field(default=None, alias="resultMode")
    program: str | None = Field(default=None, max_length=200)
    course_numbers: list[str] = Field(default_factory=list, max_length=200, alias="courseNumbers")
    study_program_names: list[str] = Field(default_factory=list, max_length=50, alias="studyProgramNames")
    specialization_names: list[str] = Field(default_factory=list, max_length=50, alias="specializationNames")
    response_language: Literal["da", "en"] | None = Field(default=None, alias="responseLanguage")


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=12)
    completed_turns: list[CompletedTurnState] = Field(default_factory=list, max_length=11, alias="completedTurns")
    academic_year: str | None = Field(default=None, pattern=r"^\d{4}-\d{4}$", alias="academicYear")

    model_config = ConfigDict(populate_by_name=True)


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


class RecommendedStudyProgram(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    degree_type: str = Field(alias="degreeType")
    description: str | None = None
    reason: str
    source_url: str = Field(alias="sourceUrl")


class StudyPlanCourseInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    course_number: str | None = Field(default=None, alias="courseNumber")
    title: str
    ects: float | None = None
    ects_options: list[float] = Field(default_factory=list, alias="ectsOptions")
    schedule: str | None = None
    requirement_role: str = Field(alias="requirementRole")
    source_url: str | None = Field(default=None, alias="sourceUrl")


class StudyPlanRequirementInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    requirement_type: str = Field(alias="requirementType")
    description: str
    required_ects: float | None = Field(default=None, alias="requiredEcts")
    required_count: int | None = Field(default=None, alias="requiredCount")
    is_subrequirement: bool = Field(default=False, alias="isSubrequirement")
    courses: list[StudyPlanCourseInfo] = Field(default_factory=list)


class StudyPlanSectionInfo(BaseModel):
    name: str
    description: str | None = None
    courses: list[StudyPlanCourseInfo] = Field(default_factory=list)
    requirements: list[StudyPlanRequirementInfo] = Field(default_factory=list)


class StudyPlanOverview(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    program_name: str = Field(alias="programName")
    degree_type: str = Field(alias="degreeType")
    academic_year: str | None = Field(default=None, alias="academicYear")
    valid_from_year: int | None = Field(default=None, alias="validFromYear")
    valid_to_year: int | None = Field(default=None, alias="validToYear")
    source_url: str = Field(alias="sourceUrl")
    sections: list[StudyPlanSectionInfo]


class SpecializationCourseInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    course_number: str | None = Field(default=None, alias="courseNumber")
    title: str
    ects: float | None = None
    schedule: str | None = None
    role: str
    is_terminated: bool = Field(default=False, alias="isTerminated")
    source_url: str | None = Field(default=None, alias="sourceUrl")


class SpecializationRequirementInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    requirement_type: str = Field(alias="requirementType")
    description: str
    required_ects: float | None = Field(default=None, alias="requiredEcts")
    required_count: int | None = Field(default=None, alias="requiredCount")
    courses: list[SpecializationCourseInfo] = Field(default_factory=list)


class SpecializationInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    program_name: str = Field(alias="programName")
    name: str
    slug: str
    is_optional: bool = Field(default=True, alias="isOptional")
    description: str | None = None
    source_url: str = Field(alias="sourceUrl")
    requirements: list[SpecializationRequirementInfo] = Field(default_factory=list)
    courses: list[SpecializationCourseInfo] = Field(default_factory=list)


class ChatResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reply: str
    understood: UnderstoodContext
    recommendations: list[RecommendedCourse] = Field(default_factory=list)
    study_programs: list[RecommendedStudyProgram] = Field(default_factory=list, alias="studyPrograms")
    study_plan: StudyPlanOverview | None = Field(default=None, alias="studyPlan")
    specializations: list[SpecializationInfo] = Field(default_factory=list)
    academic_year: str = Field(alias="academicYear")
    response_language: Literal["da", "en"] = Field(default="en", alias="responseLanguage")
    is_direct_answer: bool = Field(default=False, alias="isDirectAnswer")
    result_mode: CourseResultMode | None = Field(default=None, alias="resultMode")
    turn_state: CompletedTurnState | None = Field(default=None, alias="turnState")
