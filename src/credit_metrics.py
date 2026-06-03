from __future__ import annotations

import math
from typing import Any


EBITDA_NOT_AVAILABLE_REASON = (
    "No se identifica depreciación/amortización del período en los datos disponibles"
)


def calculate_credit_kpis(
    *,
    eerr_kpis: dict[str, Any] | None,
    balance_kpis: dict[str, Any] | None,
    comparison_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate preliminary credit KPIs from already computed EERR and Balance KPIs."""
    eerr = eerr_kpis or {}
    balance = balance_kpis or {}
    context = comparison_context or {}

    ingresos = _to_float(eerr.get("ingresos_explotacion"))
    resultado_operacional = _to_float(eerr.get("resultado_operacional"))
    margen_explotacion = _to_float(eerr.get("margen_explotacion"))
    resultado_final = _to_float(eerr.get("utilidad_perdida_ejercicio"))
    gastos_financieros = abs(_to_float(eerr.get("gastos_financieros")))

    activo_total = _to_float(balance.get("activo_total"))
    pasivo_corriente = _to_float(balance.get("pasivo_corriente"))
    patrimonio_contable = _to_float(
        balance.get("patrimonio_contable", balance.get("patrimonio"))
    )
    resultado_ejercicio = _to_float(balance.get("resultado_ejercicio"))
    patrimonio_ajustado = _to_float(
        balance.get(
            "patrimonio_ajustado_por_resultado",
            balance.get("patrimonio_mas_resultado"),
        )
    )
    capital_trabajo = _to_float(balance.get("capital_trabajo"))
    disponible_sobre_pasivo_corriente = _to_float(
        balance.get("disponible_sobre_pasivo_corriente")
    )
    inventarios_sobre_activo_corriente = _to_float(
        balance.get("inventarios_sobre_activo_corriente")
    )
    cuentas_por_cobrar_sobre_activo_corriente = _to_float(
        balance.get("cuentas_por_cobrar_sobre_activo_corriente")
    )
    deuda_corriente_sobre_patrimonio_contable = _to_float(
        balance.get(
            "deuda_corriente_sobre_patrimonio_contable",
            balance.get("deuda_corriente_sobre_patrimonio"),
        )
    )
    deuda_corriente_sobre_patrimonio_ajustado = _to_float(
        balance.get("deuda_corriente_sobre_patrimonio_ajustado")
    )
    obligaciones_bancarias_cp_sobre_pasivo_corriente = _to_float(
        balance.get("obligaciones_bancarias_cp_sobre_pasivo_corriente")
    )
    prueba_acida = _to_float(balance.get("prueba_acida"))

    margen_operacional_base = (
        resultado_operacional
        if _is_number(resultado_operacional)
        else margen_explotacion
    )

    return {
        "periodo_eerr": context.get("periodo_final"),
        "periodo_balance": balance.get("periodo"),
        "base_eerr": context.get("label"),
        "margen_operacional": _safe_div(margen_operacional_base, ingresos),
        "margen_neto": _safe_div(resultado_final, ingresos),
        "gastos_financieros_sobre_ingresos": _safe_div(gastos_financieros, ingresos),
        "gastos_financieros_bancarios_sobre_ingresos": _safe_div(
            gastos_financieros, ingresos
        ),
        "pasivo_corriente_sobre_activo_total": _safe_div(
            pasivo_corriente, activo_total
        ),
        "patrimonio_contable": patrimonio_contable,
        "resultado_ejercicio": resultado_ejercicio,
        "patrimonio_ajustado_por_resultado": patrimonio_ajustado,
        "patrimonio_contable_sobre_activo_total": _safe_div(
            patrimonio_contable, activo_total
        ),
        "patrimonio_ajustado_sobre_activo_total": _safe_div(
            patrimonio_ajustado, activo_total
        ),
        "patrimonio_mas_resultado_sobre_activo_total": _safe_div(
            patrimonio_ajustado, activo_total
        ),
        "capital_trabajo_sobre_ingresos": _safe_div(capital_trabajo, ingresos),
        "disponible_sobre_pasivo_corriente": disponible_sobre_pasivo_corriente,
        "inventarios_sobre_activo_corriente": inventarios_sobre_activo_corriente,
        "cuentas_por_cobrar_sobre_activo_corriente": cuentas_por_cobrar_sobre_activo_corriente,
        "deuda_corriente_sobre_patrimonio": deuda_corriente_sobre_patrimonio_contable,
        "deuda_corriente_sobre_patrimonio_contable": deuda_corriente_sobre_patrimonio_contable,
        "deuda_corriente_sobre_patrimonio_ajustado": deuda_corriente_sobre_patrimonio_ajustado,
        "obligaciones_bancarias_cp_sobre_pasivo_corriente": obligaciones_bancarias_cp_sobre_pasivo_corriente,
        "resultado_final_negativo": _is_number(resultado_final) and resultado_final < 0,
        "capital_trabajo_negativo": _is_number(capital_trabajo) and capital_trabajo < 0,
        "liquidez_estrecha": _is_number(prueba_acida) and prueba_acida < 1,
        "ebitda_disponible": False,
        "motivo_ebitda_no_disponible": EBITDA_NOT_AVAILABLE_REASON,
    }


def _to_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return number


def _safe_div(num: float, den: float) -> float:
    if not _is_number(num) or not _is_number(den) or den == 0:
        return float("nan")
    return num / den


def _is_number(value: Any) -> bool:
    try:
        return not math.isnan(float(value))
    except (TypeError, ValueError):
        return False
