from __future__ import annotations

import asyncio
import io
import json
import math
import re
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from api.n8n_client import post_analysis_to_n8n
from api.schemas import AnalyzeResponse
from src.adapters.kame_balance import load_kame_balance
from src.adapters.kame_eerr import load_kame_eerr
from src.adjustments import (
    apply_manual_adjustments,
    build_control_cuadratura,
    build_control_summary,
    build_manual_adjustment,
)
from src.balance_metrics import calculate_balance_kpis
from src.credit_metrics import calculate_credit_kpis
from src.metrics import (
    COMPARISON_TYPES,
    build_comparison_context,
    calculate_financial_kpis,
    compare_kpis,
    latest_period_kpis,
)


MAX_FILE_SIZE = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {".xlsx", ".xlsm"}
PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

app = FastAPI(
    title="Kappo Financial API",
    version="0.1.0",
    description="API paralela del Dashboard Financiero Kappo.",
)


class NamedBytesIO(io.BytesIO):
    def __init__(self, content: bytes, name: str):
        super().__init__(content)
        self.name = name


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "kappo-financial-api"}


@app.post("/v1/analyze", response_model=AnalyzeResponse)
async def analyze(
    eerr_file: UploadFile = File(...),
    balance_file: UploadFile = File(...),
    comparison_type: str = Form("ultimo_vs_anterior"),
    balance_period: str | None = Form(None),
    include_agent: bool = Form(False),
) -> AnalyzeResponse:
    _validate_parameters(comparison_type, balance_period)

    eerr_stream = await _read_excel(eerr_file)
    balance_stream = await _read_excel(balance_file)

    try:
        base_eerr, eerr_diagnostics = load_kame_eerr(eerr_stream)
        base_balance, balance_diagnostics = load_kame_balance(
            balance_stream,
            periodo=balance_period,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"No fue posible normalizar los archivos: {exc}",
        ) from exc

    if base_eerr.empty:
        raise HTTPException(status_code=422, detail="El EERR no generó registros.")
    if base_balance.empty:
        raise HTTPException(status_code=422, detail="El Balance no generó registros.")

    return await _build_analysis_response(
        base_eerr=base_eerr,
        eerr_diagnostics=eerr_diagnostics,
        base_balance=base_balance,
        balance_diagnostics=balance_diagnostics,
        eerr_filename=eerr_file.filename or "eerr.xlsx",
        balance_filename=balance_file.filename or "balance.xlsx",
        comparison_type=comparison_type,
        balance_period=balance_period,
        include_agent=include_agent,
        adjustments=[],
    )


@app.post("/v1/reconcile", response_model=AnalyzeResponse)
async def reconcile(
    eerr_file: UploadFile = File(...),
    balance_file: UploadFile = File(...),
    comparison_type: str = Form("ultimo_vs_anterior"),
    balance_period: str | None = Form(None),
    selected_exception_ids: str = Form("[]"),
    reason: str = Form("Ajuste manual para cuadrar suma detalle vs total Kame."),
    apply_all: bool = Form(False),
    include_agent: bool = Form(False),
) -> AnalyzeResponse:
    _validate_parameters(comparison_type, balance_period)

    eerr_stream = await _read_excel(eerr_file)
    balance_stream = await _read_excel(balance_file)

    try:
        base_eerr, eerr_diagnostics = load_kame_eerr(eerr_stream)
        base_balance, balance_diagnostics = load_kame_balance(
            balance_stream,
            periodo=balance_period,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"No fue posible normalizar los archivos: {exc}",
        ) from exc

    if base_eerr.empty:
        raise HTTPException(status_code=422, detail="El EERR no generó registros.")
    if base_balance.empty:
        raise HTTPException(status_code=422, detail="El Balance no generó registros.")

    original_exceptions = eerr_diagnostics.get("exceptions", [])
    exceptions_by_id = {
        item.get("exception_id"): item
        for item in original_exceptions
        if item.get("exception_id")
    }

    if apply_all:
        selected_ids = list(exceptions_by_id)
    else:
        selected_ids = _parse_exception_ids(selected_exception_ids)
        if not selected_ids:
            raise HTTPException(
                status_code=422,
                detail="Selecciona al menos una excepción o usa apply_all=true.",
            )

    unknown_ids = sorted(set(selected_ids) - set(exceptions_by_id))
    if unknown_ids:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Existen exception_id que no pertenecen al archivo.",
                "unknown_exception_ids": unknown_ids,
            },
        )

    adjustments = [
        build_manual_adjustment(
            exception=exceptions_by_id[exception_id],
            source_name=eerr_file.filename or "eerr.xlsx",
            motivo=reason,
            usuario="lovable_api",
        )
        for exception_id in dict.fromkeys(selected_ids)
    ]
    base_adjusted = apply_manual_adjustments(base_eerr, adjustments)
    adjusted_control = build_control_cuadratura(base_adjusted)
    adjusted_summary = build_control_summary(adjusted_control)
    pending_exceptions = _pending_exceptions_from_control(
        adjusted_control,
        original_exceptions,
    )

    return await _build_analysis_response(
        base_eerr=base_adjusted,
        eerr_diagnostics=eerr_diagnostics,
        base_balance=base_balance,
        balance_diagnostics=balance_diagnostics,
        eerr_filename=eerr_file.filename or "eerr.xlsx",
        balance_filename=balance_file.filename or "balance.xlsx",
        comparison_type=comparison_type,
        balance_period=balance_period,
        include_agent=include_agent,
        adjustments=adjustments,
        adjusted_control=adjusted_control,
        adjusted_summary=adjusted_summary,
        pending_exceptions=pending_exceptions,
    )


async def _build_analysis_response(
    *,
    base_eerr: pd.DataFrame,
    eerr_diagnostics: dict[str, Any],
    base_balance: pd.DataFrame,
    balance_diagnostics: dict[str, Any],
    eerr_filename: str,
    balance_filename: str,
    comparison_type: str,
    balance_period: str | None,
    include_agent: bool,
    adjustments: list[dict[str, Any]],
    adjusted_control: list[dict[str, Any]] | None = None,
    adjusted_summary: dict[str, Any] | None = None,
    pending_exceptions: list[dict[str, Any]] | None = None,
) -> AnalyzeResponse:
    monthly_kpis = calculate_financial_kpis(base_eerr)
    comparison_context = build_comparison_context(
        monthly_kpis,
        comparison_type,
    )
    comparison = compare_kpis(monthly_kpis, comparison_context)
    balance_kpis = calculate_balance_kpis(base_balance)

    eerr_credit_basis = comparison.get("final") or latest_period_kpis(monthly_kpis)
    credit_kpis = calculate_credit_kpis(
        eerr_kpis=eerr_credit_basis,
        balance_kpis=balance_kpis,
        comparison_context=comparison_context,
    )

    original_summary = eerr_diagnostics.get("resumen_control_cuadratura", {})
    original_status = original_summary.get("estado_general", "REVISAR")
    current_summary = adjusted_summary or original_summary
    current_control = (
        adjusted_control
        if adjusted_control is not None
        else eerr_diagnostics.get("control_cuadratura", [])
    )
    current_exceptions = (
        pending_exceptions
        if pending_exceptions is not None
        else eerr_diagnostics.get("exceptions", [])
    )
    eerr_status = current_summary.get("estado_general", "REVISAR")

    balance_control = balance_diagnostics.get("control_balance", {})
    balance_status = "OK" if balance_control.get("cuadra_balance") else "REVISAR"
    integrated_ready = eerr_status == "OK" and balance_status == "OK"
    source_base = "Base_ajustada" if adjustments else "Base_normalizada"
    agent_result = {
        "requested": include_agent,
        "status": "not_requested",
        "status_code": None,
        "error": None,
        "salud_financiera": None,
        "diagnostico": [],
        "recomendaciones": [],
        "informe": None,
    }

    if include_agent and not integrated_ready:
        agent_result.update(
            {
                "status": "blocked_by_validation",
                "error": (
                    "El análisis Kappo requiere que EERR y Balance "
                    "se encuentren validados."
                ),
            }
        )
    elif include_agent:
        n8n_payload = _build_n8n_payload(
            eerr_filename=eerr_filename,
            comparison_context=comparison_context,
            comparison=comparison,
            source_base=source_base,
            adjustments=adjustments,
            eerr_summary=current_summary,
            balance_control=balance_control,
            balance_kpis=balance_kpis,
            credit_kpis=credit_kpis,
        )
        agent_result = await asyncio.to_thread(
            post_analysis_to_n8n,
            _json_safe(n8n_payload),
        )

    result = {
        "request_id": str(uuid.uuid4()),
        "status": "ok" if integrated_ready else "review_required",
        "input": {
            "eerr_filename": eerr_filename,
            "balance_filename": balance_filename,
            "comparison_type": comparison_type,
            "balance_period": balance_period,
            "include_agent": include_agent,
        },
        "validation": {
            "integrated_ready": integrated_ready,
            "eerr": {
                "status": eerr_status,
                "periods_detected": eerr_diagnostics.get("periodos_detectados", []),
                "summary": current_summary,
                "control_details": current_control,
                "exceptions": current_exceptions,
            },
            "balance": {
                "status": balance_status,
                "period": balance_kpis.get("periodo"),
                "control": balance_control,
            },
        },
        "monthly_kpis": monthly_kpis,
        "comparison_context": comparison_context,
        "comparison": comparison,
        "balance_kpis": balance_kpis,
        "credit_kpis": credit_kpis,
        "reconciliation": {
            "required": bool(current_exceptions),
            "original_status": original_status,
            "adjusted_status": eerr_status if adjustments else None,
            "pending_count": len(current_exceptions),
            "applied_count": len(adjustments),
            "can_apply_all": bool(current_exceptions),
            "source_base": source_base,
            "differences": _reconciliation_differences(current_exceptions),
            "applied_adjustments": adjustments,
        },
        "agent": agent_result,
    }
    return AnalyzeResponse.model_validate(_json_safe(result))


def _build_n8n_payload(
    *,
    eerr_filename: str,
    comparison_context: dict[str, Any],
    comparison: dict[str, Any],
    source_base: str,
    adjustments: list[dict[str, Any]],
    eerr_summary: dict[str, Any],
    balance_control: dict[str, Any],
    balance_kpis: dict[str, Any],
    credit_kpis: dict[str, Any],
) -> dict[str, Any]:
    return {
        "origen": "dashboard_evolutivo_financiero_kappo_api",
        "nombre_archivo": eerr_filename,
        "tipo_comparacion": comparison_context.get("label"),
        "enfoque_analisis": "Ejecutivo general",
        "fuente_base": source_base,
        "ajustes_aplicados": len(adjustments),
        "balance_disponible": bool(balance_kpis),
        "balance_kpis": balance_kpis,
        "credit_kpis": credit_kpis,
        "control_balance": balance_control,
        "periodo_base": comparison_context.get("periodo_inicial"),
        "periodo_actual": comparison_context.get("periodo_final"),
        "control_cuadratura": eerr_summary,
        "kpis": {
            "base": comparison.get("initial", {}),
            "actual": comparison.get("final", {}),
            "variacion": comparison.get("delta", {}),
            "variacion_margen_pp": comparison.get("margin_delta_pp"),
        },
        "alertas": [],
        "lectura_ejecutiva_actual": [],
    }


def _validate_parameters(
    comparison_type: str,
    balance_period: str | None,
) -> None:
    if comparison_type not in COMPARISON_TYPES:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Tipo de comparación no válido.",
                "allowed": list(COMPARISON_TYPES),
            },
        )
    if balance_period and not PERIOD_PATTERN.match(balance_period):
        raise HTTPException(
            status_code=422,
            detail="balance_period debe tener formato YYYY-MM.",
        )


def _parse_exception_ids(raw_value: str) -> list[str]:
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail="selected_exception_ids debe ser un arreglo JSON.",
        ) from exc
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise HTTPException(
            status_code=422,
            detail="selected_exception_ids debe contener solo strings.",
        )
    return list(dict.fromkeys(value))


def _pending_exceptions_from_control(
    adjusted_control: list[dict[str, Any]],
    original_exceptions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    original_by_key = {
        (str(item.get("periodo", "")), str(item.get("grupo", ""))): item
        for item in original_exceptions
    }
    pending = []
    for row in adjusted_control:
        if row.get("cuadra"):
            continue
        periodo = str(row.get("periodo", ""))
        grupo = str(row.get("grupo", ""))
        original = original_by_key.get((periodo, grupo), {})
        difference = float(row.get("diferencia", 0) or 0)
        pending.append(
            {
                **original,
                "exception_id": original.get("exception_id")
                or f"reconciliation__{periodo}__{grupo}",
                "periodo": periodo,
                "grupo": grupo,
                "estado": "pendiente",
                "diferencia": difference,
                "mensaje": (
                    f"El grupo '{grupo}' no cuadra en el periodo {periodo}: "
                    f"suma detalle {row.get('suma_detalle')} vs total normalizado "
                    f"{row.get('total_kame_normalizado')}."
                ),
                "contexto": {
                    "suma_detalle": row.get("suma_detalle"),
                    "total_kame_normalizado": row.get("total_kame_normalizado"),
                    "cuadra": False,
                },
            }
        )
    return pending


def _reconciliation_differences(
    exceptions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for exception in exceptions:
        context = exception.get("contexto") or {}
        difference = float(exception.get("diferencia", 0) or 0)
        rows.append(
            {
                "exception_id": exception.get("exception_id"),
                "periodo": exception.get("periodo"),
                "grupo": exception.get("grupo"),
                "suma_detalle": context.get("suma_detalle"),
                "total_normalizado": context.get("total_kame_normalizado"),
                "diferencia": difference,
                "ajuste_sugerido": -difference,
                "mensaje": exception.get("mensaje"),
                "estado": exception.get("estado", "pendiente"),
            }
        )
    return rows


async def _read_excel(upload: UploadFile) -> NamedBytesIO:
    filename = upload.filename or ""
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Solo se aceptan archivos .xlsx o .xlsm.",
        )

    content = await upload.read()
    if not content:
        raise HTTPException(status_code=422, detail=f"{filename} está vacío.")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"{filename} supera el límite de 20 MB.",
        )

    return NamedBytesIO(content, filename)


def _json_safe(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return _json_safe(value.to_dict(orient="records"))
    if isinstance(value, pd.Series):
        return _json_safe(value.to_dict())
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
