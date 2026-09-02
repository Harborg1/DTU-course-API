from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class CourseData(BaseModel):
    course_number: str
    academic_year: str
    university: str = "dtu"
    programme_level_code: str | None = None
    teaching_language_code: str | None = None
    location_code: str | None = None
    study_board_code: str | None = None
    title: str
    title_da: str | None = None
    title_en: str | None = None
    ects: Decimal | None = None
    level: str | None = None
    course_type: str | None = None
    language: str | None = None
    department: str | None = None
    department_code: str | None = None
    period: str | None = None
    schedule: str | None = None
    campus: str | None = None
    prerequisites: str | None = None
    prerequisites_da: str | None = None
    prerequisites_en: str | None = None
    mandatory_prerequisites: str | None = None
    mandatory_prerequisites_da: str | None = None
    mandatory_prerequisites_en: str | None = None
    exam: str | None = None
    evaluation: str | None = None
    description: str | None = None
    description_da: str | None = None
    description_en: str | None = None
    content: str | None = None
    content_da: str | None = None
    content_en: str | None = None
    learning_objectives: str | None = None
    learning_objectives_da: str | None = None
    learning_objectives_en: str | None = None
    teaching_methods: str | None = None
    teaching_methods_da: str | None = None
    teaching_methods_en: str | None = None
    literature: str | None = None
    literature_da: str | None = None
    literature_en: str | None = None
    course_responsible: str | None = None
    teachers: str | None = None
    registration_requirements: str | None = None
    remarks: str | None = None
    remarks_da: str | None = None
    remarks_en: str | None = None
    schedules: list[str] = Field(default_factory=list)
    responsible_people: list[dict] = Field(default_factory=list)
    examinations: list[dict] = Field(default_factory=list)
    no_credit_with: list[str] = Field(default_factory=list)
    previous_course_numbers: list[str] = Field(default_factory=list)
    recommended_prerequisite_course_numbers: list[str] = Field(default_factory=list)
    source_url: str
    source_last_updated: datetime | None = None

    @field_validator("course_number")
    @classmethod
    def validate_course_number(cls, value: str) -> str:
        value = value.strip().upper()
        if not value or len(value) > 16 or not value.replace("-", "").isalnum():
            raise ValueError("invalid DTU course number")
        return value

    @field_validator("academic_year")
    @classmethod
    def validate_academic_year(cls, value: str) -> str:
        parts = value.split("-")
        if len(parts) != 2 or not all(part.isdigit() and len(part) == 4 for part in parts):
            raise ValueError("academic year must have the form YYYY-YYYY")
        if int(parts[1]) != int(parts[0]) + 1:
            raise ValueError("academic year must cover consecutive years")
        return value

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("course title is required")
        return value.strip()

    @field_validator("ects")
    @classmethod
    def validate_ects(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and (value < 0 or value > 120):
            raise ValueError("ECTS must be between 0 and 120")
        return value


class CourseSummary(ApiModel):
    course_number: str = Field(alias="courseNumber")
    title: str
    ects: float | None = None
    level: str | None = None
    period: str | None = None
    schedule: str | None = None
    language: str | None = None
    department: str | None = None
    campus: str | None = None
    description: str | None = None
    relevance_score: float | None = Field(default=None, alias="relevanceScore")
    source_url: str = Field(alias="sourceUrl")


class CourseDetail(ApiModel):
    id: int
    course_number: str = Field(alias="courseNumber")
    academic_year: str = Field(alias="academicYear")
    title: str
    title_da: str | None = Field(default=None, alias="titleDa")
    title_en: str | None = Field(default=None, alias="titleEn")
    ects: float | None = None
    level: str | None = None
    course_type: str | None = Field(default=None, alias="courseType")
    language: str | None = None
    department: str | None = None
    department_code: str | None = Field(default=None, alias="departmentCode")
    period: str | None = None
    schedule: str | None = None
    campus: str | None = None
    prerequisites: str | None = None
    prerequisites_da: str | None = Field(default=None, alias="prerequisitesDa")
    prerequisites_en: str | None = Field(default=None, alias="prerequisitesEn")
    mandatory_prerequisites: str | None = Field(default=None, alias="mandatoryPrerequisites")
    mandatory_prerequisites_da: str | None = Field(default=None, alias="mandatoryPrerequisitesDa")
    mandatory_prerequisites_en: str | None = Field(default=None, alias="mandatoryPrerequisitesEn")
    exam: str | None = None
    evaluation: str | None = None
    description: str | None = None
    description_da: str | None = Field(default=None, alias="descriptionDa")
    description_en: str | None = Field(default=None, alias="descriptionEn")
    content: str | None = None
    content_da: str | None = Field(default=None, alias="contentDa")
    content_en: str | None = Field(default=None, alias="contentEn")
    learning_objectives: str | None = Field(default=None, alias="learningObjectives")
    learning_objectives_da: str | None = Field(default=None, alias="learningObjectivesDa")
    learning_objectives_en: str | None = Field(default=None, alias="learningObjectivesEn")
    teaching_methods_da: str | None = Field(default=None, alias="teachingMethodsDa")
    teaching_methods_en: str | None = Field(default=None, alias="teachingMethodsEn")
    literature_da: str | None = Field(default=None, alias="literatureDa")
    literature_en: str | None = Field(default=None, alias="literatureEn")
    course_responsible: str | None = Field(default=None, alias="courseResponsible")
    teachers: str | None = None
    registration_requirements: str | None = Field(default=None, alias="registrationRequirements")
    remarks: str | None = None
    remarks_da: str | None = Field(default=None, alias="remarksDa")
    remarks_en: str | None = Field(default=None, alias="remarksEn")
    schedules: list[str]
    responsible_people: list[dict] = Field(alias="responsiblePeople")
    examinations: list[dict]
    no_credit_with: list[str] = Field(alias="noCreditWith")
    previous_course_numbers: list[str] = Field(alias="previousCourseNumbers")
    recommended_prerequisite_course_numbers: list[str] = Field(
        alias="recommendedPrerequisiteCourseNumbers"
    )
    source_url: str = Field(alias="sourceUrl")
    source_last_updated: datetime | None = Field(default=None, alias="sourceLastUpdated")
    imported_at: datetime = Field(alias="importedAt")
    updated_at: datetime = Field(alias="updatedAt")
