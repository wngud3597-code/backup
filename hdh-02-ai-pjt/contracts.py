from pydantic import BaseModel, Field


# 1. 기술 항목 메타데이터
class TechnologyItem(BaseModel):
    technology_id: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    category: str
    description: str
    source_ref: str = "Stack Overflow Developer Survey 2026"


# 2. 통계 관측치
class ObservationRecord(BaseModel):
    technology_id: str
    category_id: str
    year: int = 2026
    population_id: str = "all_respondents"
    usage_pct: float | None = None
    desired_pct: float | None = None
    admired_pct: float | None = None
    question_n: int = 14099
    source_locator: str


# 3. 정형 통계 조회 결과
class StatisticalResult(BaseModel):
    result_id: str
    technology_id: str
    technology_name: str
    category: str
    year: int
    population: str
    usage_pct: float | None
    desired_pct: float | None
    admired_pct: float | None
    question_n: int
    source_locator: str


# 4. 근거 조각
class Evidence(BaseModel):
    evidence_no: int
    kind: str  # item_metadata, survey_statistics, survey_context, supporting_doc
    title: str
    text: str
    locator: str
    provenance_id: str


# 5. 문장 단위 답변 및 인용
class SentenceCitation(BaseModel):
    text: str
    citations: list[int] = Field(default_factory=list)


# 6. 최종 생성 답변
class AnswerResult(BaseModel):
    status: str  # answered, partial, insufficient
    sentences: list[SentenceCitation] = Field(default_factory=list)
    statistical_card: dict | None = None
    limitations: str | None = None
