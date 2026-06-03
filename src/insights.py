from __future__ import annotations

import math

import pandas as pd


def generate_executive_reading(kpis: pd.DataFrame) -> list[str]:
    if kpis is None or kpis.empty:
        return ["No hay datos suficientes para generar lectura ejecutiva."]

    ordered = kpis.sort_values("periodo").reset_index(drop=True)
    last = ordered.iloc[-1]
    prev = ordered.iloc[-2] if len(ordered) >= 2 else None
    insights: list[str] = []

    if prev is not None:
        ingresos_delta = _num(last["ingresos_explotacion"]) - _num(prev["ingresos_explotacion"])
        insights.append(
            f"Los ingresos {_verb_delta(ingresos_delta)} {format_currency_abs(ingresos_delta)} "
            "respecto al mes anterior."
        )

        margin_delta_pp = (_num(last["margen_pct"]) - _num(prev["margen_pct"])) * 100
        insights.append(
            f"El margen de explotación cerró en {format_percent(last['margen_pct'])}, "
            f"{_margin_comparison(margin_delta_pp)}."
        )

        gastos_delta = abs(_num(last["gastos_administracion_ventas"])) - abs(
            _num(prev["gastos_administracion_ventas"])
        )
        insights.append(
            f"Los gastos de administración y ventas {_verb_delta(gastos_delta)} "
            f"{format_currency_abs(gastos_delta)} frente al mes anterior."
        )
    else:
        insights.append(
            f"El período {_text(last['periodo'])} cuenta con ingresos por "
            f"{format_currency(_num(last['ingresos_explotacion']))}."
        )
        insights.append(
            f"El margen de explotación cerró en {format_percent(last['margen_pct'])}."
        )

    result = _num(last["utilidad_perdida_ejercicio"])
    result_status = "positivo" if result >= 0 else "negativo"
    insights.append(f"El resultado final del período fue {result_status}: {format_currency(result)}.")

    alerts = build_financial_alerts(kpis)
    for _, alert in alerts.head(2).iterrows():
        insights.append(str(alert["detalle"]))

    return insights[:6]


def generate_comparison_reading(comparison: dict) -> list[str]:
    if not comparison:
        return ["No hay datos suficientes para generar lectura ejecutiva."]

    label = comparison.get("label", "comparación seleccionada")
    initial_label = comparison.get("periodo_inicial", "período inicial")
    final_label = comparison.get("periodo_final", "período final")
    initial = comparison.get("initial", {})
    final = comparison.get("final", {})
    delta = comparison.get("delta", {})
    margin_delta_pp = _num(comparison.get("margin_delta_pp"))

    insights = [f"Lectura basada en: {label} ({initial_label} vs {final_label})."]
    ingresos_delta = _num(delta.get("ingresos_explotacion"))
    insights.append(
        f"Los ingresos {_verb_delta(ingresos_delta)} {format_currency_abs(ingresos_delta)} "
        "en la comparación seleccionada."
    )

    insights.append(
        f"El margen de explotación final cerró en {format_percent(final.get('margen_pct'))}, "
        f"{_margin_comparison_context(margin_delta_pp)}."
    )

    gastos_delta = abs(_num(final.get("gastos_administracion_ventas"))) - abs(
        _num(initial.get("gastos_administracion_ventas"))
    )
    insights.append(
        f"Los gastos de administración y ventas {_verb_delta(gastos_delta)} "
        f"{format_currency_abs(gastos_delta)} en la comparación seleccionada."
    )

    result = _num(final.get("utilidad_perdida_ejercicio"))
    result_status = "positivo" if result >= 0 else "negativo"
    insights.append(f"El resultado final comparado fue {result_status}: {format_currency(result)}.")
    return insights[:6]


def build_financial_alerts(kpis: pd.DataFrame) -> pd.DataFrame:
    columns = ["periodo", "severidad", "indicador", "alerta", "valor", "umbral", "detalle"]
    if kpis is None or kpis.empty:
        return pd.DataFrame(columns=columns)

    ordered = kpis.sort_values("periodo").reset_index(drop=True)
    last = ordered.iloc[-1]
    prev = ordered.iloc[-2] if len(ordered) >= 2 else None
    period = _text(last["periodo"])
    rows: list[dict[str, object]] = []

    margin = _num(last["margen_pct"])
    if not _is_nan(margin) and margin < 0.40:
        rows.append(
            _alert(
                period,
                "Alta",
                "Margen %",
                "Margen bajo",
                format_percent(margin),
                "< 40.0%",
                f"Alerta: el margen de explotación es bajo ({format_percent(margin)}).",
            )
        )

    result = _num(last["utilidad_perdida_ejercicio"])
    if not _is_nan(result) and result < 0:
        rows.append(
            _alert(
                period,
                "Alta",
                "Resultado final",
                "Resultado negativo",
                format_currency(result),
                "< $0",
                f"Alerta: el resultado final del período fue negativo ({format_currency(result)}).",
            )
        )

    if prev is not None:
        prev_margin = _num(prev["margen_pct"])
        margin_delta_pp = (margin - prev_margin) * 100
        if not _is_nan(margin_delta_pp) and margin_delta_pp < -5:
            rows.append(
                _alert(
                    period,
                    "Media",
                    "Margen %",
                    "Caida de margen",
                    f"{margin_delta_pp:,.1f} pp",
                    "< -5.0 pp",
                    f"Alerta: el margen bajo {abs(margin_delta_pp):,.1f} puntos porcentuales vs el mes anterior.",
                )
            )

        gastos_now = abs(_num(last["gastos_administracion_ventas"]))
        gastos_prev = abs(_num(prev["gastos_administracion_ventas"]))
        gastos_change = _safe_div(gastos_now - gastos_prev, gastos_prev)
        if not _is_nan(gastos_change) and gastos_change > 0.20:
            rows.append(
                _alert(
                    period,
                    "Media",
                    "Gastos administración y ventas",
                    "Aumento de gastos",
                    format_percent(gastos_change),
                    "> 20.0%",
                    f"Alerta: los gastos de administración y ventas subieron {format_percent(gastos_change)}.",
                )
            )

        result_prev = _num(prev["utilidad_perdida_ejercicio"])
        result_delta = result - result_prev
        if not _is_nan(result_delta) and result_delta < 0:
            rows.append(
                _alert(
                    period,
                    "Media",
                    "Resultado final",
                    "Resultado cae",
                    format_currency(result_delta),
                    "< $0 vs mes anterior",
                    f"Alerta: el resultado final cayo {format_currency_abs(result_delta)} respecto al mes anterior.",
                )
            )

        ingresos_now = _num(last["ingresos_explotacion"])
        ingresos_prev = _num(prev["ingresos_explotacion"])
        ingresos_change = _safe_div(ingresos_now - ingresos_prev, ingresos_prev)
        if not _is_nan(ingresos_change) and ingresos_change < -0.15:
            rows.append(
                _alert(
                    period,
                    "Media",
                    "Ingresos",
                    "Ingresos en caida",
                    format_percent(ingresos_change),
                    "< -15.0%",
                    f"Alerta: los ingresos bajaron {format_percent(abs(ingresos_change))} frente al mes anterior.",
                )
            )

    return pd.DataFrame(rows, columns=columns)


def format_currency(value: float | int | None) -> str:
    value = _num(value)
    if _is_nan(value):
        return "N/D"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}"


def format_currency_abs(value: float | int | None) -> str:
    value = _num(value)
    if _is_nan(value):
        return "N/D"
    return f"${abs(value):,.0f}"


def format_signed_currency(value: float | int | None) -> str:
    value = _num(value)
    if _is_nan(value):
        return "N/D"
    sign = "+" if value > 0 else ""
    return f"{sign}{format_currency(value)}"


def format_percent(value: float | int | None) -> str:
    value = _num(value)
    if _is_nan(value):
        return "N/D"
    return f"{value * 100:,.1f}%"


def format_signed_percent_points(value: float | int | None) -> str:
    value = _num(value)
    if _is_nan(value):
        return "N/D"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.1f} pp"


def _alert(
    period: str,
    severity: str,
    indicator: str,
    alert: str,
    value: str,
    threshold: str,
    detail: str,
) -> dict[str, object]:
    return {
        "periodo": period,
        "severidad": severity,
        "indicador": indicator,
        "alerta": alert,
        "valor": value,
        "umbral": threshold,
        "detalle": detail,
    }


def _verb_delta(value: float) -> str:
    if _is_nan(value) or value == 0:
        return "se mantuvieron en"
    return "aumentaron en" if value > 0 else "disminuyeron en"


def _margin_comparison(delta_pp: float) -> str:
    if _is_nan(delta_pp) or abs(delta_pp) < 0.05:
        return "en linea con el mes anterior"
    if delta_pp > 0:
        return f"{format_signed_percent_points(delta_pp)} por sobre el mes anterior"
    return f"{format_signed_percent_points(delta_pp)} por debajo del mes anterior"


def _margin_comparison_context(delta_pp: float) -> str:
    if _is_nan(delta_pp) or abs(delta_pp) < 0.05:
        return "en linea con la base comparativa"
    if delta_pp > 0:
        return f"{format_signed_percent_points(delta_pp)} por sobre la base comparativa"
    return f"{format_signed_percent_points(delta_pp)} por debajo de la base comparativa"


def _safe_div(num: float, den: float) -> float:
    if _is_nan(num) or _is_nan(den) or den == 0:
        return float("nan")
    return num / den


def _num(value: object) -> float:
    try:
        value_float = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return value_float


def _is_nan(value: float | int | None) -> bool:
    if value is None:
        return True
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return True


def _text(value: object) -> str:
    return "" if value is None else str(value)
