from __future__ import annotations

from enum import Enum
from typing import List
from pydantic import BaseModel, Field


class EvalStatus(str, Enum):
    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"
    UNKNOWN = "unknown"


class SqlLengthStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    UNKNOWN = "unknown"


class MatchStatus(str, Enum):
    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"
    UNKNOWN = "unknown"


class FailureType(str, Enum):
    NONE = "none"
    RUN_FAILURE = "run_failure"
    SQL_SAFETY = "sql_safety"
    SQL_LOGIC = "sql_logic"
    RESULT_MISMATCH = "result_mismatch"
    ANSWER_MISMATCH = "answer_mismatch"
    FORMAT_ISSUE = "format_issue"
    UNSUPPORTED_HANDLING = "unsupported_handling"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class RecommendedActionType(str, Enum):
    NONE = "none"
    REVIEW_SQL = "review_sql"
    REVIEW_PROMPT = "review_prompt"
    REVIEW_BACKEND = "review_backend"
    ADD_TEST_CASE = "add_test_case"
    ADD_SKILL_RULE = "add_skill_rule"


class OverallEvaluation(BaseModel):
    model_config = {"extra": "forbid"}

    final_status: EvalStatus = Field(
        description="Overall evaluation status for this benchmark row."
    )
    final_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall score between 0.0 and 1.0."
    )
    failure_type: FailureType = Field(
        description="Primary failure category, or none when the row passes."
    )
    failure_reason: str = Field(
        description="Short explanation for the final status."
    )


class RunStatusCheck(BaseModel):
    model_config = {"extra": "forbid"}

    status: EvalStatus = Field(
        description="Whether silver and actual run statuses are acceptable."
    )
    silver_run_status: str | None = Field(
        default=None,
        description="Run status from the silver-truth run."
    )
    actual_run_status: str | None = Field(
        default=None,
        description="Run status from the actual production-model run."
    )
    reason: str = Field(
        description="Short explanation of run status comparison."
    )


class SqlSafetyCheck(BaseModel):
    model_config = {"extra": "forbid"}

    status: EvalStatus = Field(
        description="SQL safety validation status."
    )
    sql_length_status: SqlLengthStatus = Field(
        description="SQL length status based on configured thresholds."
    )
    sql_length_chars: int = Field(
        ge=0,
        description="Character length of the actual SQL."
    )
    read_only: bool = Field(
        description="True if SQL is read-only SELECT or WITH ... SELECT."
    )
    single_statement: bool = Field(
        description="True if SQL contains only one statement."
    )
    uses_select_star: bool = Field(
        description="True if SQL uses SELECT *."
    )
    has_org_id_param: bool = Field(
        description="True if SQL includes :org_id."
    )
    has_clerk_org_filter: bool = Field(
        description="True if SQL filters by clerk_org_id."
    )
    has_soft_delete_filter: bool = Field(
        description="True if SQL includes is_deleted = false when required."
    )
    uses_allowed_tables_only: bool = Field(
        description="True if SQL only uses tables allowed by the expected skill."
    )
    exposes_sensitive_fields: bool = Field(
        description="True if SQL selects secrets, credentials, raw payloads, or private fields."
    )
    contact_fields_allowed: bool = Field(
        description="True if email/phone usage is allowed or not present."
    )
    errors: List[str] = Field(
        default_factory=list,
        description="List of SQL safety errors."
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="List of SQL safety warnings."
    )


class SqlSemanticCheck(BaseModel):
    model_config = {"extra": "forbid"}

    status: EvalStatus = Field(
        description="Semantic comparison status between silver SQL and actual SQL."
    )
    same_business_intent: bool = Field(
        description="True if both SQL queries answer the same business intent."
    )
    same_metric: bool = Field(
        description="True if both SQL queries compute the same metric."
    )
    same_filters: bool = Field(
        description="True if both SQL queries use equivalent filters."
    )
    same_grouping: bool = Field(
        description="True if both SQL queries use equivalent grouping logic."
    )
    same_output_type: bool = Field(
        description="True if both SQL queries return the same output type."
    )
    same_date_logic: bool = Field(
        description="True if both SQL queries use equivalent date/time logic."
    )
    same_limit_logic: bool = Field(
        description="True if both SQL queries use equivalent limit behavior when relevant."
    )
    same_percentage_or_trend_logic: bool = Field(
        description="True if percentage or trend logic matches when relevant."
    )
    reason: str = Field(
        description="Short explanation of SQL semantic comparison."
    )


class ResultCheck(BaseModel):
    model_config = {"extra": "forbid"}

    status: EvalStatus = Field(
        description="Result comparison status."
    )
    row_count_match: bool = Field(
        description="True if silver and actual row counts match."
    )
    value_match: MatchStatus = Field(
        description="Whether result values match. Use unknown if result JSON is unavailable."
    )
    category_match: MatchStatus = Field(
        description="Whether grouped categories match. Use unknown if not applicable or unavailable."
    )
    list_record_match: MatchStatus = Field(
        description="Whether list records match. Use unknown if not applicable or unavailable."
    )
    trend_match: MatchStatus = Field(
        description="Whether trend periods/counts/percentages match. Use unknown if not applicable or unavailable."
    )
    reason: str = Field(
        description="Short explanation of result comparison."
    )


class AnswerCheck(BaseModel):
    model_config = {"extra": "forbid"}

    status: EvalStatus = Field(
        description="Final answer comparison status."
    )
    score: float = Field(
        ge=0.0,
        le=1.0,
        description="Answer-level score between 0.0 and 1.0."
    )
    same_business_meaning: bool = Field(
        description="True if actual answer has the same business meaning as silver answer."
    )
    numbers_match: MatchStatus = Field(
        description="Whether numbers in the actual answer match the silver answer."
    )
    categories_match: MatchStatus = Field(
        description="Whether category/status/source labels match."
    )
    records_match: MatchStatus = Field(
        description="Whether listed records match when evidence is available."
    )
    trend_insight_correct: MatchStatus = Field(
        description="Whether trend increase/decrease insight is correct."
    )
    format_ok: bool = Field(
        description="True if answer formatting matches the expected output type."
    )
    unsafe_content: bool = Field(
        description="True if answer exposes unsafe/private data."
    )
    mentions_sql_or_tool_output: bool = Field(
        description="True if answer unnecessarily mentions SQL or tool output."
    )
    reason: str = Field(
        description="Short explanation of answer comparison."
    )


class RecommendedAction(BaseModel):
    model_config = {"extra": "forbid"}

    action: RecommendedActionType = Field(
        description="Recommended next action based on the evaluation."
    )
    details: str = Field(
        description="Short recommendation for debugging or improvement."
    )


class SqlAnswerEvaluation(BaseModel):
    model_config = {"extra": "forbid"}

    question_id: str = Field(
        description="Question ID from the benchmark CSV."
    )
    overall: OverallEvaluation
    run_status_check: RunStatusCheck
    sql_safety_check: SqlSafetyCheck
    sql_semantic_check: SqlSemanticCheck
    result_check: ResultCheck
    answer_check: AnswerCheck
    recommended_action: RecommendedAction