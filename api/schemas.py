from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class InputSummary(BaseModel):
    eerr_filename: str
    balance_filename: str
    comparison_type: str
    balance_period: str | None = None
    include_agent: bool = False


class EerrValidation(BaseModel):
    status: Literal["OK", "REVISAR"]
    periods_detected: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    control_details: list[dict[str, Any]] = Field(default_factory=list)
    exceptions: list[dict[str, Any]] = Field(default_factory=list)


class BalanceValidation(BaseModel):
    status: Literal["OK", "REVISAR"]
    period: str | None = None
    control: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    integrated_ready: bool
    eerr: EerrValidation
    balance: BalanceValidation


class AgentResult(BaseModel):
    requested: bool
    status: Literal[
        "not_requested",
        "not_configured",
        "blocked_by_validation",
        "ok",
        "timeout",
        "http_error",
        "connection_error",
        "error",
    ]
    status_code: int | None = None
    error: str | None = None
    salud_financiera: Any | None = None
    diagnostico: list[Any] = Field(default_factory=list)
    recomendaciones: list[Any] = Field(default_factory=list)
    informe: str | None = None


class ReconciliationResult(BaseModel):
    required: bool
    original_status: Literal["OK", "REVISAR"]
    adjusted_status: Literal["OK", "REVISAR"] | None = None
    pending_count: int
    applied_count: int
    can_apply_all: bool
    source_base: Literal["Base_normalizada", "Base_ajustada"]
    differences: list[dict[str, Any]] = Field(default_factory=list)
    applied_adjustments: list[dict[str, Any]] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    request_id: str
    status: Literal["ok", "review_required"]
    input: InputSummary
    validation: ValidationResult
    monthly_kpis: list[dict[str, Any]]
    comparison_context: dict[str, Any]
    comparison: dict[str, Any]
    balance_kpis: dict[str, Any]
    credit_kpis: dict[str, Any]
    reconciliation: ReconciliationResult
    agent: AgentResult
