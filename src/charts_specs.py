from __future__ import annotations

import math

import pandas as pd


def build_financial_line_options(kpis: pd.DataFrame) -> dict:
    periods = _periods(kpis)
    return {
        "tooltip": {"trigger": "axis", "valueFormatter": _currency_js_formatter()},
        "legend": {"top": 0, "data": ["Ingresos", "Margen explotacion", "Resultado final"]},
        "grid": {"left": 56, "right": 24, "top": 56, "bottom": 36},
        "xAxis": {"type": "category", "data": periods},
        "yAxis": {"type": "value", "axisLabel": {"formatter": "${value}"}},
        "series": [
            {
                "name": "Ingresos",
                "type": "line",
                "smooth": True,
                "data": _series(kpis, "ingresos_explotacion"),
                "lineStyle": {"width": 3, "color": "#2d5016"},
                "itemStyle": {"color": "#2d5016"},
            },
            {
                "name": "Margen explotacion",
                "type": "line",
                "smooth": True,
                "data": _series(kpis, "margen_explotacion"),
                "lineStyle": {"width": 3, "color": "#4a7c2a"},
                "itemStyle": {"color": "#4a7c2a"},
            },
            {
                "name": "Resultado final",
                "type": "line",
                "smooth": True,
                "data": _series(kpis, "utilidad_perdida_ejercicio"),
                "lineStyle": {"width": 3, "color": "#26415a"},
                "itemStyle": {"color": "#26415a"},
            },
        ],
    }


def build_admin_expenses_bar_options(kpis: pd.DataFrame) -> dict:
    periods = _periods(kpis)
    return {
        "tooltip": {"trigger": "axis", "valueFormatter": _currency_js_formatter()},
        "grid": {"left": 56, "right": 24, "top": 32, "bottom": 36},
        "xAxis": {"type": "category", "data": periods},
        "yAxis": {"type": "value", "axisLabel": {"formatter": "${value}"}},
        "series": [
            {
                "name": "Gastos adm. y ventas",
                "type": "bar",
                "data": _series(kpis, "gastos_administracion_ventas", absolute=True),
                "barMaxWidth": 44,
                "itemStyle": {"color": "#6c757d", "borderRadius": [4, 4, 0, 0]},
            }
        ],
    }


def _periods(kpis: pd.DataFrame) -> list[str]:
    if kpis is None or kpis.empty or "periodo" not in kpis.columns:
        return []
    return [str(value) for value in kpis["periodo"].tolist()]


def _series(kpis: pd.DataFrame, column: str, *, absolute: bool = False) -> list[float | None]:
    if kpis is None or kpis.empty or column not in kpis.columns:
        return []
    values = []
    for value in pd.to_numeric(kpis[column], errors="coerce").tolist():
        if value is None or math.isnan(float(value)):
            values.append(None)
        else:
            value = float(value)
            values.append(abs(value) if absolute else value)
    return values


def _currency_js_formatter() -> str:
    return "function (value) { return '$' + Number(value || 0).toLocaleString('es-CL'); }"
