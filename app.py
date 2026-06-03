import json
import html
import inspect
import importlib
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd
import streamlit as st

from src.adjustments import (
    ajustes_to_dataframe,
    apply_manual_adjustments,
    build_control_cuadratura as build_adjusted_control_cuadratura,
    build_control_summary as build_adjusted_control_summary,
    build_manual_adjustment,
)
from src.adapters.kame_balance import load_kame_balance
from src.adapters.kame_eerr import load_kame_eerr
from src.balance_metrics import calculate_balance_kpis
from src.charts_specs import build_admin_expenses_bar_options, build_financial_line_options
from src.credit_metrics import calculate_credit_kpis
from src.exports import build_analysis_workbook
from src.formatting import (
    format_alerts_table,
    format_clp,
    format_control_table,
    format_group_summary_table,
    format_kpis_table,
    format_pct,
    format_ranking_table,
    format_signed_clp,
)
from src import insights as insights_module
from src.insights import (
    build_financial_alerts,
    generate_executive_reading,
)
from src import metrics as metrics_module
from src.pdf_exports import build_kappo_ai_report_pdf
from src.theme import apply_kappo_theme, render_header, section_title

try:
    from streamlit_echarts import st_echarts
except Exception:
    st_echarts = None


COMPARISON_TYPES = getattr(
    metrics_module,
    "COMPARISON_TYPES",
    {
        "ultimo_vs_anterior": "Último mes vs mes anterior",
        "ultimo_vs_inicio": "Último mes vs inicio del año actual",
        "ultimo_vs_primer_cargado": "Último mes vs primer período cargado",
        "mismo_mes_anio_anterior": "Mismo mes año anterior vs mes actual",
        "acumulado_anual": "Acumulado año actual vs acumulado año anterior",
    },
)
calculate_financial_kpis = metrics_module.calculate_financial_kpis
latest_period_kpis = metrics_module.latest_period_kpis

N8N_WEBHOOK_URL = "https://henry0101.app.n8n.cloud/webhook/5c9fd568-e386-4018-9c0b-b5d5bc3451ea"


def _expense_abs_delta(kpis, column):
    if kpis is None or len(kpis) < 2 or column not in kpis.columns:
        return None
    ordered = kpis.sort_values("periodo").reset_index(drop=True)
    last_value = ordered.iloc[-1][column]
    prev_value = ordered.iloc[-2][column]
    return abs(float(last_value)) - abs(float(prev_value))


def _build_comparison_context_compatible(kpis, comparison_type):
    builder = getattr(metrics_module, "build_comparison_context", None)
    if callable(builder):
        return builder(kpis, comparison_type)
    periods = sorted(kpis["periodo"].dropna().astype(str).unique()) if kpis is not None and not kpis.empty else []
    label = COMPARISON_TYPES.get(comparison_type, comparison_type)
    unavailable = {
        "key": comparison_type,
        "label": label,
        "available": False,
        "message": "No hay datos suficientes para esta comparación.",
    }
    if len(periods) < 2:
        return unavailable
    latest = periods[-1]
    latest_year, latest_month = _split_period(latest)
    if comparison_type == "ultimo_vs_anterior":
        return _period_context(comparison_type, label, periods[-2], latest)
    if comparison_type == "ultimo_vs_inicio":
        current_year_periods = [p for p in periods if _split_period(p)[0] == latest_year]
        if not current_year_periods:
            return {
                **unavailable,
                "message": f"No hay períodos disponibles para el año {latest_year}.",
            }
        return _period_context(comparison_type, label, current_year_periods[0], latest)
    if comparison_type == "ultimo_vs_primer_cargado":
        return _period_context(comparison_type, label, periods[0], latest)
    if comparison_type == "mismo_mes_anio_anterior":
        base_period = f"{latest_year - 1}-{latest_month:02d}"
        if base_period not in periods:
            return {
                **unavailable,
                "message": f"No existe el mismo mes del año anterior ({base_period}) para compararlo con {latest}.",
            }
        return _period_context(comparison_type, label, base_period, latest)
    if comparison_type == "acumulado_anual":
        current = [p for p in periods if _split_period(p)[0] == latest_year]
        months = {_split_period(p)[1] for p in current}
        previous = [p for p in periods if _split_period(p)[0] == latest_year - 1 and _split_period(p)[1] in months]
        if not current or not previous:
            return {
                **unavailable,
                "message": f"No hay períodos acumulados comparables para {latest_year - 1} y {latest_year}.",
            }
        return {
            "key": comparison_type,
            "label": label,
            "available": True,
            "mode": "accumulated",
            "periodo_inicial": f"Acumulado {latest_year - 1}",
            "periodo_final": f"Acumulado {latest_year}",
            "initial_periods": previous,
            "final_periods": current,
            "message": "",
        }
    return unavailable


def _compare_kpis_compatible(kpis, context):
    comparer = getattr(metrics_module, "compare_kpis", None)
    if callable(comparer):
        return comparer(kpis, context)
    if kpis is None or kpis.empty or not context.get("available"):
        return {}
    if context.get("mode") == "period":
        initial = _kpi_row(kpis, context["periodo_inicial"])
        final = _kpi_row(kpis, context["periodo_final"])
    else:
        initial = _kpi_accum(kpis, context["initial_periods"])
        final = _kpi_accum(kpis, context["final_periods"])
    delta_keys = [
        "ingresos_explotacion",
        "margen_explotacion",
        "gastos_administracion_ventas",
        "utilidad_perdida_ejercicio",
    ]
    return {
        "label": context["label"],
        "periodo_inicial": context["periodo_inicial"],
        "periodo_final": context["periodo_final"],
        "initial": initial,
        "final": final,
        "delta": {key: final.get(key, 0.0) - initial.get(key, 0.0) for key in delta_keys},
        "margin_delta_pp": (final.get("margen_pct", 0.0) - initial.get("margen_pct", 0.0)) * 100,
    }


def _rank_account_movements_for_context_compatible(base, context, top_n=10):
    ranker = getattr(metrics_module, "rank_account_movements_for_context", None)
    if callable(ranker):
        return ranker(base, context, top_n=top_n)
    columns = [
        "grupo",
        "cuenta",
        "periodo_inicial",
        "monto_inicial",
        "periodo_final",
        "monto_final",
        "variacion_abs",
        "variacion_pct",
    ]
    if base is None or base.empty or not context.get("available"):
        empty = pd.DataFrame(columns=columns)
        return empty, empty
    initial_periods = context.get("initial_periods", [context.get("periodo_inicial")])
    final_periods = context.get("final_periods", [context.get("periodo_final")])
    detail = base.loc[base["nivel"] == "detalle"].copy()
    initial = (
        detail.loc[detail["periodo"].isin(initial_periods)]
        .groupby(["grupo", "cuenta"], as_index=False)["monto"]
        .sum()
        .rename(columns={"monto": "monto_inicial"})
    )
    final = (
        detail.loc[detail["periodo"].isin(final_periods)]
        .groupby(["grupo", "cuenta"], as_index=False)["monto"]
        .sum()
        .rename(columns={"monto": "monto_final"})
    )
    out = initial.merge(final, on=["grupo", "cuenta"], how="outer").fillna(0.0)
    out["periodo_inicial"] = context["periodo_inicial"]
    out["periodo_final"] = context["periodo_final"]
    out["variacion_abs"] = out["monto_final"] - out["monto_inicial"]
    out["variacion_pct"] = out.apply(lambda row: _safe_div(row["variacion_abs"], abs(row["monto_inicial"])), axis=1)
    ranked = out[columns].sort_values("variacion_abs", ascending=False)
    return ranked.head(top_n).reset_index(drop=True), ranked.sort_values("variacion_abs").head(top_n).reset_index(drop=True)


def _period_context(key, label, initial, final):
    return {
        "key": key,
        "label": label,
        "available": True,
        "mode": "period",
        "periodo_inicial": initial,
        "periodo_final": final,
        "initial_periods": [initial],
        "final_periods": [final],
        "message": "",
    }


def _kpi_row(kpis, period):
    row = kpis.loc[kpis["periodo"].astype(str) == str(period)]
    return row.iloc[0].to_dict() if not row.empty else {}


def _kpi_accum(kpis, periods):
    scoped = kpis.loc[kpis["periodo"].isin(periods)].copy()
    ingresos = float(scoped["ingresos_explotacion"].sum())
    margen = float(scoped["margen_explotacion"].sum())
    return {
        "ingresos_explotacion": ingresos,
        "margen_explotacion": margen,
        "margen_pct": _safe_div(margen, ingresos),
        "gastos_administracion_ventas": float(scoped["gastos_administracion_ventas"].sum()),
        "utilidad_perdida_ejercicio": float(scoped["utilidad_perdida_ejercicio"].sum()),
    }


def _safe_div(num, den):
    return float("nan") if den in (0, 0.0) else float(num) / float(den)


def _split_period(period):
    year, month = str(period).split("-", 1)
    return int(year), int(month)


def _build_export_workbook_compatible(
    *,
    base_normalizada,
    kpis,
    diagnostics,
    mayores_aumentos,
    mayores_disminuciones,
    lectura_ejecutiva,
    alertas_financieras,
):
    kwargs = {
        "base_normalizada": base_normalizada,
        "kpis_mensuales": kpis,
        "control_cuadratura": diagnostics.get("control_cuadratura", []),
        "ranking_aumentos": mayores_aumentos,
        "ranking_disminuciones": mayores_disminuciones,
        "diagnostics": diagnostics,
    }
    accepted_params = inspect.signature(build_analysis_workbook).parameters
    if "lectura_ejecutiva" in accepted_params:
        kwargs["lectura_ejecutiva"] = lectura_ejecutiva
    if "alertas_financieras" in accepted_params:
        kwargs["alertas_financieras"] = alertas_financieras
    return build_analysis_workbook(**kwargs)


def build_n8n_payload(
    *,
    nombre_archivo,
    comparison_context,
    comparison_values,
    diagnostics,
    alertas_financieras,
    lectura_ejecutiva,
    enfoque_analisis,
    balance_kpis=None,
    credit_kpis=None,
    diagnostics_balance=None,
):
    return _json_safe(
        {
            "origen": "dashboard_evolutivo_financiero_kappo",
            "nombre_archivo": nombre_archivo,
            "tipo_comparacion": comparison_context.get("label"),
            "enfoque_analisis": enfoque_analisis,
            "fuente_base": diagnostics.get("base_de_analisis", "Base_normalizada"),
            "ajustes_aplicados": len(diagnostics.get("ajustes_usuario", [])),
            "balance_disponible": bool(balance_kpis),
            "balance_kpis": balance_kpis or {},
            "credit_kpis": credit_kpis or {},
            "control_balance": (diagnostics_balance or {}).get("control_balance", {}),
            "periodo_base": comparison_context.get("periodo_inicial"),
            "periodo_actual": comparison_context.get("periodo_final"),
            "control_cuadratura": diagnostics.get("resumen_control_cuadratura", {}),
            "kpis": {
                "base": comparison_values.get("initial", {}),
                "actual": comparison_values.get("final", {}),
                "variacion": comparison_values.get("delta", {}),
                "variacion_margen_pp": comparison_values.get("margin_delta_pp"),
            },
            "alertas": _dataframe_records(alertas_financieras),
            "lectura_ejecutiva_actual": lectura_ejecutiva,
        }
    )


def _post_json_to_n8n(payload):
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        N8N_WEBHOOK_URL,
        data=encoded,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body


def _parse_n8n_response(response_body):
    if not response_body:
        return {}
    try:
        parsed = json.loads(response_body)
    except json.JSONDecodeError:
        return {"informe": response_body}
    if isinstance(parsed, list) and parsed:
        parsed = parsed[0]
    return parsed if isinstance(parsed, dict) else {"informe": str(parsed)}


def _render_n8n_analysis(response_body):
    parsed = _parse_n8n_response(response_body)
    informe = parsed.get("informe")
    salud = parsed.get("salud_financiera")
    if not informe and not salud:
        st.caption("n8n no devolvió un informe para mostrar.")
        return parsed
    badge = ""
    if _has_meaningful_value(salud):
        badge = f'<div class="ai-health-badge">{html.escape(str(salud))}</div>'
    body = _format_ai_report_html(str(informe or "Sin informe disponible."))
    st.markdown(
        '<div class="ai-analysis-card">'
        '<div class="ai-analysis-title">Análisis Kappo</div>'
        f"{badge}"
        f'<div class="ai-analysis-body">{body}</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    return parsed


def _build_ai_report_pdf_bytes(parsed_response, payload):
    from src import pdf_exports

    importlib.reload(pdf_exports)
    kwargs = {
        "informe": str(parsed_response.get("informe") or "Sin informe disponible."),
        "salud_financiera": parsed_response.get("salud_financiera"),
        "nombre_archivo": payload.get("nombre_archivo", "N/D"),
        "tipo_comparacion": payload.get("tipo_comparacion", "N/D"),
        "periodo_base": payload.get("periodo_base", "N/D"),
        "periodo_actual": payload.get("periodo_actual", "N/D"),
        "fuente_base": payload.get("fuente_base", "Base_normalizada"),
        "estado_cuadratura": (payload.get("control_cuadratura") or {}).get("estado_general", "N/D"),
        "ajustes_aplicados": int(payload.get("ajustes_aplicados", 0) or 0),
        "kpis": payload.get("kpis", {}),
        "balance_kpis": payload.get("balance_kpis", {}),
        "credit_kpis": payload.get("credit_kpis", {}),
        "control_balance": payload.get("control_balance", {}),
    }
    pdf_builder = pdf_exports.build_kappo_ai_report_pdf
    accepted_params = inspect.signature(pdf_builder).parameters
    return pdf_builder(
        **{key: value for key, value in kwargs.items() if key in accepted_params}
    )


def _has_meaningful_value(value):
    if value is None:
        return False
    text = str(value).strip()
    return bool(text) and text.lower() not in {"n/d", "nd", "none", "null", "nan", "-"}


def _format_ai_report_html(report):
    lines = [line.strip() for line in str(report).replace("\r\n", "\n").split("\n")]
    parts = []
    bullet_items = []

    def flush_bullets():
        nonlocal bullet_items
        if bullet_items:
            parts.append("<ul>" + "".join(f"<li>{item}</li>" for item in bullet_items) + "</ul>")
            bullet_items = []

    for line in lines:
        if not line:
            flush_bullets()
            continue
        clean = line.strip()
        normalized = clean.rstrip(":").strip().lower()
        if _is_ai_section_heading(normalized, clean):
            flush_bullets()
            parts.append(f"<h4>{html.escape(clean.rstrip(':'))}</h4>")
            continue
        if clean.startswith(("-", "â€¢", "*")):
            bullet_items.append(html.escape(clean.lstrip("-â€¢* ").strip()))
            continue
        parts.append(f"<p>{html.escape(clean)}</p>")
    flush_bullets()
    return "".join(parts)


def _is_ai_section_heading(normalized, original):
    known = {
        "resumen ejecutivo",
        "puntos relevantes",
        "alertas o riesgos",
        "alertas",
        "riesgos",
        "recomendación",
        "recomendaciones",
        "diagnóstico",
        "diagnostico",
    }
    if normalized in known:
        return True
    if original.endswith(":") and len(original) <= 80:
        return True
    if len(original) <= 80 and original[:2].isdigit() and "." in original[:4]:
        return True
    return False


def _dataframe_records(df):
    if df is None or df.empty:
        return []
    return _json_safe(df.to_dict(orient="records"))


def _json_safe(value):
    if isinstance(value, pd.DataFrame):
        return _json_safe(value.to_dict(orient="records"))
    if isinstance(value, pd.Series):
        return _json_safe(value.to_dict())
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if pd.isna(value) if not isinstance(value, (dict, list, tuple)) else False:
        return None
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    return value


def _generate_comparison_reading_compatible(comparison):
    generator = getattr(insights_module, "generate_comparison_reading", None)
    if callable(generator):
        return generator(comparison)
    if not comparison:
        return ["No hay datos suficientes para generar lectura ejecutiva."]

    label = comparison.get("label", "comparación seleccionada")
    initial_label = comparison.get("periodo_inicial", "período inicial")
    final_label = comparison.get("periodo_final", "período final")
    initial = comparison.get("initial", {})
    final = comparison.get("final", {})
    delta = comparison.get("delta", {})
    margin_delta_pp = comparison.get("margin_delta_pp")

    return [
        f"Lectura basada en: {label} ({initial_label} vs {final_label}).",
        f"Los ingresos variaron {format_signed_clp(delta.get('ingresos_explotacion'))} "
        "en la comparación seleccionada.",
        f"El margen final cerró en {format_pct(final.get('margen_pct'))}.",
        f"Los gastos de administración y ventas pasaron de "
        f"{format_clp(initial.get('gastos_administracion_ventas'))} a "
        f"{format_clp(final.get('gastos_administracion_ventas'))}.",
        f"El resultado final comparado fue {format_clp(final.get('utilidad_perdida_ejercicio'))}.",
        f"La variación de margen fue {margin_delta_pp:,.1f} pp.",
    ]


COMPARISON_CARD_CONFIGS = [
    ("Ingresos", "ingresos_explotacion", "money"),
    ("Margen explotación", "margen_explotacion", "money"),
    ("Margen %", "margen_pct", "percent"),
    ("Gastos adm. y ventas", "gastos_administracion_ventas", "money"),
    ("Resultado final", "utilidad_perdida_ejercicio", "money"),
]


def _render_comparison_cards(comparison):
    if not comparison:
        st.info("No hay datos suficientes para mostrar tarjetas comparativas.")
        return

    initial = comparison.get("initial", {})
    final = comparison.get("final", {})
    delta = comparison.get("delta", {})
    initial_label = comparison.get("periodo_inicial", "Período base")
    final_label = comparison.get("periodo_final", "Período actual")

    first_row = st.columns(3, gap="large")
    second_row = st.columns(2, gap="large")
    columns = [*first_row, *second_row]
    for column, (title, key, value_type) in zip(columns, COMPARISON_CARD_CONFIGS):
        base_value = _num_or_nan(initial.get(key))
        final_value = _num_or_nan(final.get(key))
        if key == "margen_pct":
            delta_value = (final_value - base_value) * 100
            delta_label = _format_pp(delta_value)
            delta_pct_label = None
            delta_label_text = "Variación"
        else:
            delta_value = _num_or_nan(delta.get(key, final_value - base_value))
            delta_label = _format_signed_clp_chilean(delta_value)
            delta_pct_label = _format_variation_pct(delta_value, base_value)
            delta_label_text = "Variación $"

        delta_class = _delta_class(delta_value)
        with column:
            st.markdown(
                _comparison_card_html(
                    title=title,
                    initial_label=initial_label,
                    base_value=base_value,
                    final_label=final_label,
                    final_value=final_value,
                    value_type=value_type,
                    delta_label_text=delta_label_text,
                    delta_label=delta_label,
                    delta_pct_label=delta_pct_label,
                    delta_class=delta_class,
                ),
                unsafe_allow_html=True,
            )


def _comparison_card_html(
    *,
    title,
    initial_label,
    base_value,
    final_label,
    final_value,
    value_type,
    delta_label_text,
    delta_label,
    delta_pct_label,
    delta_class,
):
    rows = [
        '<div class="comparison-card">',
        f'<div class="comparison-card-title">{html.escape(str(title))}</div>',
        '<div class="comparison-period-block">',
        '<div class="comparison-period-line">',
        '<span class="comparison-period-label">Base</span>',
        f'<span class="comparison-period">{html.escape(str(initial_label))}</span>',
        "</div>",
        f'<span class="comparison-main-value">{_format_card_value(base_value, value_type)}</span>',
        "</div>",
        '<div class="comparison-period-block">',
        '<div class="comparison-period-line">',
        '<span class="comparison-period-label">Actual</span>',
        f'<span class="comparison-period">{html.escape(str(final_label))}</span>',
        "</div>",
        f'<span class="comparison-main-value">{_format_card_value(final_value, value_type)}</span>',
        "</div>",
        '<div class="comparison-row">',
        f'<span class="comparison-label">{html.escape(str(delta_label_text))}</span>',
        f'<span class="comparison-value {delta_class}">{html.escape(str(delta_label))}</span>',
        "</div>",
    ]
    if delta_pct_label is not None:
        rows.extend(
            [
                '<div class="comparison-row">',
                '<span class="comparison-label">Variación %</span>',
                f'<span class="comparison-value {delta_class}">{html.escape(str(delta_pct_label))}</span>',
                "</div>",
            ]
        )
    rows.append("</div>")
    return "".join(rows)


def _build_comparison_alerts(comparison):
    columns = ["periodo", "severidad", "indicador", "alerta", "valor", "umbral", "detalle"]
    if not comparison:
        return pd.DataFrame(columns=columns)

    initial = comparison.get("initial", {})
    final = comparison.get("final", {})
    delta = comparison.get("delta", {})
    period = str(comparison.get("periodo_final", "comparación"))
    rows = []

    margin = _num_or_nan(final.get("margen_pct"))
    if not pd.isna(margin) and margin < 0.40:
        rows.append(
            _alert_row(
                period,
                "Alta",
                "Margen %",
                "Margen bajo",
                format_pct(margin),
                "< 40.0%",
                f"Alerta: el margen de explotación es bajo en la comparación seleccionada ({format_pct(margin)}).",
            )
        )

    margin_delta_pp = _num_or_nan(comparison.get("margin_delta_pp"))
    if not pd.isna(margin_delta_pp) and margin_delta_pp < -5:
        rows.append(
            _alert_row(
                period,
                "Media",
                "Margen %",
                "Caida de margen",
                _format_pp(margin_delta_pp),
                "< -5.0 pp",
                f"Alerta: el margen bajó {abs(margin_delta_pp):,.1f} puntos porcentuales en la comparación seleccionada.",
            )
        )

    gastos_initial = abs(_num_or_nan(initial.get("gastos_administracion_ventas")))
    gastos_final = abs(_num_or_nan(final.get("gastos_administracion_ventas")))
    gastos_change = _safe_div(gastos_final - gastos_initial, gastos_initial)
    if not pd.isna(gastos_change) and gastos_change > 0.20:
        rows.append(
            _alert_row(
                period,
                "Media",
                "Gastos administración y ventas",
                "Aumento de gastos",
                _format_plain_pct(gastos_change),
                "> 20.0%",
                f"Alerta: los gastos de administración y ventas subieron {_format_plain_pct(gastos_change)} en la comparación seleccionada.",
            )
        )

    result = _num_or_nan(final.get("utilidad_perdida_ejercicio"))
    if not pd.isna(result) and result < 0:
        rows.append(
            _alert_row(
                period,
                "Alta",
                "Resultado final",
                "Resultado negativo",
                format_clp(result),
                "< $0",
                f"Alerta: el resultado final comparado fue negativo ({format_clp(result)}).",
            )
        )

    result_delta = _num_or_nan(delta.get("utilidad_perdida_ejercicio"))
    if not pd.isna(result_delta) and result_delta < 0:
        rows.append(
            _alert_row(
                period,
                "Media",
                "Resultado final",
                "Resultado cae",
                format_signed_clp(result_delta),
                "< $0 vs base",
                f"Alerta: el resultado final cayo {format_clp(abs(result_delta))} frente a la base seleccionada.",
            )
        )

    ingresos_initial = _num_or_nan(initial.get("ingresos_explotacion"))
    ingresos_delta = _num_or_nan(delta.get("ingresos_explotacion"))
    ingresos_change = _safe_div(ingresos_delta, ingresos_initial)
    if not pd.isna(ingresos_change) and ingresos_change < -0.15:
        rows.append(
            _alert_row(
                period,
                "Media",
                "Ingresos",
                "Ingresos en caida",
                _format_plain_pct(ingresos_change),
                "< -15.0%",
                f"Alerta: los ingresos bajaron {_format_plain_pct(abs(ingresos_change))} frente a la base seleccionada.",
            )
        )

    return pd.DataFrame(rows, columns=columns)


def _executive_reading_table(insights):
    rows = []
    for index, insight in enumerate(insights, start=1):
        rows.append(
            {
                "N°": index,
                "Tema": _insight_topic(insight),
                "Lectura ejecutiva": insight,
            }
        )
    return pd.DataFrame(rows, columns=["N°", "Tema", "Lectura ejecutiva"])


def _style_executive_reading_table(df):
    return (
        df.style.hide(axis="index")
        .set_properties(
            subset=["Tema"],
            **{
                "font-weight": "700",
                "color": "#203047",
                "background-color": "#f1f5f8",
            },
        )
        .set_properties(
            subset=["Lectura ejecutiva"],
            **{
                "white-space": "normal",
                "line-height": "1.35",
            },
        )
        .set_table_styles(
            [
                {"selector": "th", "props": [("background-color", "#e8f4dc"), ("color", "#203047")]},
                {"selector": "td", "props": [("border-color", "#dde5ee")]},
            ]
        )
    )


def _style_alerts_table(df):
    if df is None or df.empty:
        return df

    def style_severity(value):
        text = str(value).lower()
        if "alta" in text:
            return "background-color: #fde7e7; color: #9f1d1d; font-weight: 800;"
        if "media" in text:
            return "background-color: #fff3cd; color: #7a4f00; font-weight: 800;"
        return "background-color: #edf2f7; color: #495057; font-weight: 800;"

    styler = (
        df.style.hide(axis="index")
        .set_properties(
            subset=[col for col in ["Detalle", "Alerta"] if col in df.columns],
            **{"white-space": "normal", "line-height": "1.35"},
        )
        .set_table_styles(
            [
                {"selector": "th", "props": [("background-color", "#e8f4dc"), ("color", "#203047")]},
                {"selector": "td", "props": [("border-color", "#dde5ee")]},
            ]
        )
    )
    if "Severidad" in df.columns:
        styler = styler.map(style_severity, subset=["Severidad"])
    return styler


def _insight_topic(insight):
    text = str(insight).lower()
    if "lectura basada" in text:
        return "Base comparativa"
    if "ingresos" in text:
        return "Ingresos"
    if "margen" in text:
        return "Margen"
    if "gastos" in text:
        return "Gastos"
    if "resultado" in text:
        return "Resultado final"
    return "Observación"


def _render_executive_reading_card(insights, context, comparison):
    subtitle = _comparison_subtitle(context)
    clean_insights = [
        str(insight)
        for insight in insights
        if not str(insight).lower().startswith("lectura basada")
    ]
    if not clean_insights:
        clean_insights = [str(insight) for insight in insights]
    items = "".join(
        '<div class="insight-item"><span class="insight-dot"></span>'
        f"<span>{html.escape(insight)}</span></div>"
        for insight in clean_insights
    )
    conclusion = _executive_conclusion(comparison)
    card = (
        '<div class="executive-card">'
        '<div class="executive-title">Lectura ejecutiva</div>'
        f'<div class="executive-subtitle">{html.escape(subtitle)}</div>'
        f'<div class="insight-list">{items}</div>'
        '<div class="executive-conclusion">'
        "<strong>Conclusión</strong>"
        f"<span>{html.escape(conclusion)}</span>"
        "</div>"
        "</div>"
    )
    st.markdown(card, unsafe_allow_html=True)


def _render_alert_cards(alerts):
    if alerts is None or alerts.empty:
        st.markdown(
            '<div class="alert-ok-box">Sin alertas financieras relevantes para la comparación seleccionada.</div>',
            unsafe_allow_html=True,
        )
        return
    cards = []
    for _, row in alerts.iterrows():
        severity = str(row.get("severidad", "Baja"))
        severity_key = _severity_key(severity)
        cards.append(
            f'<div class="alert-card alert-card-{severity_key}">'
            f'<span class="alert-badge alert-badge-{severity_key}">{html.escape(severity)}</span>'
            f'<div class="alert-heading">{html.escape(str(row.get("indicador", "")))} · {html.escape(str(row.get("alerta", "")))}</div>'
            f'<div class="alert-meta">Valor: <strong>{html.escape(str(row.get("valor", "")))}</strong> · Umbral: {html.escape(str(row.get("umbral", "")))}</div>'
            f'<div class="alert-detail">{html.escape(str(row.get("detalle", "")))}</div>'
            "</div>"
        )
    st.markdown(f'<div class="alerts-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def _render_ranking_card(title, ranking):
    subtitle = "Top cuentas detalle según la comparación seleccionada"
    if ranking is None or ranking.empty:
        st.markdown(
            '<div class="ranking-card">'
            f'<div class="ranking-title">{html.escape(title)}</div>'
            f'<div class="ranking-subtitle">{html.escape(subtitle)}</div>'
            '<div class="alert-ok-box">No hay suficientes períodos para calcular este ranking.</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        return
    rows = []
    for _, row in ranking.iterrows():
        period = f"{row.get('periodo_inicial', '')} â†’ {row.get('periodo_final', '')}"
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('grupo', '')))}</td>"
            f'<td class="ranking-account">{html.escape(str(row.get("cuenta", "")))}</td>'
            f"<td>{html.escape(period)}</td>"
            f'<td class="ranking-money">{html.escape(_format_signed_clp_chilean(row.get("variacion_abs")))}</td>'
            f'<td class="ranking-pct">{html.escape(_format_plain_pct(row.get("variacion_pct")))}</td>'
            "</tr>"
        )
    table = (
        '<table class="ranking-table">'
        "<thead><tr><th>Grupo</th><th>Cuenta</th><th>Período</th><th>Variación $</th><th>Variación %</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    st.markdown(
        '<div class="ranking-card">'
        f'<div class="ranking-title">{html.escape(title)}</div>'
        f'<div class="ranking-subtitle">{html.escape(subtitle)}</div>'
        f"{table}</div>",
        unsafe_allow_html=True,
    )


def _comparison_subtitle(context):
    if not context or not context.get("available"):
        return "Comparación no disponible"
    return (
        f"{context.get('label', 'Comparación seleccionada')} · "
        f"{context.get('periodo_inicial', '')} vs {context.get('periodo_final', '')}"
    )


def _executive_conclusion(comparison):
    if not comparison:
        return "No hay datos suficientes para concluir sobre la comparación seleccionada."
    final = comparison.get("final", {})
    delta = comparison.get("delta", {})
    result = _num_or_nan(final.get("utilidad_perdida_ejercicio"))
    margin_delta = _num_or_nan(comparison.get("margin_delta_pp"))
    expenses_delta = _num_or_nan(delta.get("gastos_administracion_ventas"))
    if result >= 0 and margin_delta >= 0 and expenses_delta <= 0:
        return "El período muestra mejora operacional, resultado positivo y gastos contenidos."
    if result >= 0 and expenses_delta > 0:
        return "El período muestra resultado positivo, aunque con presión al alza en gastos."
    if result >= 0:
        return "El período mantiene resultado positivo, con desempeño operativo favorable."
    return "El período requiere revisión ejecutiva por resultado final negativo o deterioro operativo."


def _severity_key(severity):
    text = str(severity).lower()
    if "alta" in text:
        return "high"
    if "media" in text:
        return "medium"
    if "ok" in text:
        return "ok"
    return "low"


def _alert_row(period, severity, indicator, alert, value, threshold, detail):
    return {
        "periodo": period,
        "severidad": severity,
        "indicador": indicator,
        "alerta": alert,
        "valor": value,
        "umbral": threshold,
        "detalle": detail,
    }


def _format_card_value(value, value_type):
    if value_type == "percent":
        return html.escape(format_pct(value))
    return html.escape(_format_clp_chilean(value))


def _format_variation_pct(delta, base):
    pct = _safe_div(delta, abs(base))
    return _format_plain_pct(pct)


def _format_clp_chilean(value):
    value = _num_or_nan(value)
    if pd.isna(value):
        return "N/D"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}".replace(",", ".")


def _format_signed_clp_chilean(value):
    value = _num_or_nan(value)
    if pd.isna(value):
        return "N/D"
    if value > 0:
        return f"+{_format_clp_chilean(value)}"
    return _format_clp_chilean(value)


def _format_plain_pct(value):
    value = _num_or_nan(value)
    if pd.isna(value):
        return "N/D"
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:,.1f}%"


def _format_pp(value):
    value = _num_or_nan(value)
    if pd.isna(value):
        return "N/D"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.1f} pp"


def _format_ratio(value):
    value = _num_or_nan(value)
    if pd.isna(value):
        return "N/D"
    return f"{value:,.2f}"


def _format_percent_from_ratio(value):
    value = _num_or_nan(value)
    if pd.isna(value):
        return "N/D"
    return f"{value * 100:,.1f}%"


def _delta_class(value):
    value = _num_or_nan(value)
    if pd.isna(value) or abs(value) < 0.000001:
        return "comparison-delta-neutral"
    return "comparison-delta-positive" if value > 0 else "comparison-delta-negative"


def _num_or_nan(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _source_session_key(nombre_archivo, diagnostics):
    periods = ",".join(diagnostics.get("periodos_detectados", []))
    return f"{nombre_archivo}|{diagnostics.get('filas')}|{diagnostics.get('columnas')}|{periods}"


def _reset_adjustments_for_source(source_key):
    if st.session_state.get("adjustments_source_key") != source_key:
        st.session_state["adjustments_source_key"] = source_key
        st.session_state["ajustes_usuario"] = []


def _build_adjusted_diagnostics(diagnostics, control_ajustado, resumen_ajustado, ajustes_usuario):
    adjusted = dict(diagnostics)
    adjusted["control_cuadratura_original"] = diagnostics.get("control_cuadratura", [])
    adjusted["resumen_control_cuadratura_original"] = diagnostics.get(
        "resumen_control_cuadratura", {}
    )
    adjusted["control_cuadratura"] = control_ajustado
    adjusted["resumen_control_cuadratura"] = resumen_ajustado
    adjusted["ajustes_usuario"] = ajustes_usuario
    adjusted["base_de_analisis"] = "Base_ajustada" if ajustes_usuario else "Base_normalizada"
    adjusted["filas_base_ajustada"] = adjusted.get("filas_base_normalizada", 0) + len(ajustes_usuario)
    return adjusted


def _render_reconciliation_center(
    *,
    exceptions,
    ajustes_usuario,
    nombre_archivo,
    base_ajustada,
    control_original,
    resumen_original,
    resumen_ajustado,
):
    has_adjustments = bool(ajustes_usuario)
    applied_exception_ids = {
        ajuste.get("exception_id")
        for ajuste in ajustes_usuario
        if ajuste.get("estado") == "aplicado"
    }
    pending_exceptions = [
        exception
        for exception in exceptions
        if exception.get("exception_id") not in applied_exception_ids
    ]
    has_exceptions = bool(pending_exceptions)
    if not has_exceptions and not has_adjustments:
        return

    if resumen_ajustado.get("estado_general") == "OK" and has_adjustments:
        st.success("Base ajustada cuadrada. El analisis se recalcula sobre Base_ajustada.")
    elif has_exceptions:
        st.warning(
            f"Control cuadratura en revision: {len(pending_exceptions)} diferencias pendientes. "
            "Abre el Centro de conciliacion para revisar o aplicar ajustes."
        )

    with st.expander("Centro de conciliacion", expanded=False):
        col_original, col_adjusted, col_adjustments = st.columns(3)
        col_original.metric("Estado original", resumen_original.get("estado_general", "N/D"))
        col_adjusted.metric("Estado ajustado", resumen_ajustado.get("estado_general", "N/D"))
        col_adjustments.metric("Ajustes aplicados", len(ajustes_usuario))

        if has_exceptions:
            rows = []
            for exception in pending_exceptions:
                context = exception.get("contexto") or {}
                diferencia = float(exception.get("diferencia", 0) or 0)
                rows.append(
                    {
                        "Aplicar": False,
                        "exception_id": exception.get("exception_id"),
                        "Periodo": exception.get("periodo"),
                        "Grupo": exception.get("grupo"),
                        "Suma detalle": context.get("suma_detalle"),
                        "Total Kame": context.get("total_kame_normalizado"),
                        "Diferencia": diferencia,
                        "Ajuste sugerido": -diferencia,
                        "Impacto": "Cuadra detalle contra total; KPIs ejecutivos usan total/resultado",
                    }
                )
            diff_df = pd.DataFrame(rows)
            display_df = diff_df.copy()
            for column in ["Suma detalle", "Total Kame", "Diferencia", "Ajuste sugerido"]:
                display_df[column] = display_df[column].map(format_clp)
            display_df = display_df.drop(columns=["exception_id"])

            st.markdown("#### Diferencias pendientes del archivo original")
            quick_col, manual_col = st.columns([1, 2])
            with quick_col:
                if st.button("Aplicar todos los ajustes pendientes"):
                    existing = {
                        ajuste.get("exception_id")
                        for ajuste in ajustes_usuario
                        if ajuste.get("estado") == "aplicado"
                    }
                    for exception in pending_exceptions:
                        if exception.get("exception_id") in existing:
                            continue
                        st.session_state["ajustes_usuario"].append(
                            build_manual_adjustment(
                                exception=exception,
                                source_name=nombre_archivo,
                                motivo="Ajuste manual masivo para cuadrar suma detalle vs total Kame.",
                            )
                        )
                    st.rerun()
            with manual_col:
                st.caption(
                    "Usa la tabla solo si quieres aplicar una seleccion parcial."
                )

            edited_df = st.data_editor(
                display_df,
                use_container_width=True,
                hide_index=True,
                disabled=[
                    "Periodo",
                    "Grupo",
                    "Suma detalle",
                    "Total Kame",
                    "Diferencia",
                    "Ajuste sugerido",
                    "Impacto",
                ],
                column_config={
                    "Aplicar": st.column_config.CheckboxColumn(
                        "Aplicar",
                        help="Marca las diferencias que deseas corregir con ajuste manual.",
                    )
                },
                key="pending_adjustments_editor",
            )

            st.caption(
                "Los ajustes seleccionados se agregan como cuenta detalle 'Ajuste manual de cuadratura'. "
                "La Base_normalizada original queda intacta."
            )
            motivo = st.text_input(
                "Motivo para los ajustes seleccionados",
                value="Ajuste manual para cuadrar suma detalle vs total Kame.",
            )
            selected_mask = edited_df["Aplicar"].astype(bool) if "Aplicar" in edited_df else []
            selected_ids = diff_df.loc[selected_mask, "exception_id"].tolist()
            st.write("Ajustes seleccionados:", len(selected_ids))

            if st.button("Aplicar ajustes seleccionados y recalcular", type="primary"):
                existing = {
                    ajuste.get("exception_id")
                    for ajuste in ajustes_usuario
                    if ajuste.get("estado") == "aplicado"
                }
                selected_by_id = {
                    exception.get("exception_id"): exception
                    for exception in pending_exceptions
                }
                for exception_id in selected_ids:
                    if exception_id in existing:
                        continue
                    st.session_state["ajustes_usuario"].append(
                        build_manual_adjustment(
                            exception=selected_by_id[exception_id],
                            source_name=nombre_archivo,
                            motivo=motivo,
                        )
                    )
                st.rerun()

        if has_adjustments:
            st.markdown("#### Ajustes aplicados")
            adjustments_df = ajustes_to_dataframe(ajustes_usuario).copy()
            if "monto" in adjustments_df.columns:
                adjustments_df["monto"] = adjustments_df["monto"].map(format_clp)
            visible = [
                "ajuste_id",
                "periodo",
                "grupo",
                "cuenta",
                "monto",
                "motivo",
                "estado",
                "exception_id",
            ]
            st.dataframe(adjustments_df[visible], use_container_width=True, hide_index=True)
            if st.button("Revertir todos los ajustes"):
                st.session_state["ajustes_usuario"] = []
                st.rerun()

        with st.expander("Control de cuadratura ajustado", expanded=False):
            st.markdown("#### Control original")
            st.dataframe(format_control_table(control_original), use_container_width=True, hide_index=True)
            st.markdown("#### Control ajustado")
            control_adjusted = build_adjusted_control_cuadratura(base_ajustada)
            st.dataframe(format_control_table(control_adjusted), use_container_width=True, hide_index=True)


def _render_loading_status_card(*, has_eerr_file, has_balance_file, has_analysis=False):
    def status_item(label, state):
        icon = {
            "cargado": "&#10003;",
            "disponible": "&#10003;",
            "pendiente": "&hellip;",
            "bloqueado": "&#128274;",
        }.get(state, "&hellip;")
        class_name = (
            "ok"
            if state in {"cargado", "disponible"}
            else "locked"
            if state == "bloqueado"
            else "pending"
        )
        return (
            '<div class="load-status-item">'
            f'<div class="load-status-label"><span class="load-status-icon load-status-{class_name}">{icon}</span>{html.escape(label)}</div>'
            f'<div class="load-status-value">{html.escape(state.capitalize())}</div>'
            '</div>'
        )

    eerr_status = "cargado" if has_eerr_file else "pendiente"
    balance_status = "cargado" if has_balance_file else "pendiente"
    analysis_status = "disponible" if has_eerr_file and has_balance_file else "bloqueado"
    pdf_status = "disponible" if has_analysis else "bloqueado"
    st.markdown(
        f"""
        <div class="executive-card">
            <div class="executive-title">Estado de carga</div>
            <div class="executive-subtitle">Para el informe integrado se requieren ambos archivos.</div>
            <div class="load-status-grid">
                {status_item("Estado de Resultados", eerr_status)}
                {status_item("Balance Clasificado", balance_status)}
                {status_item("Análisis Kappo", analysis_status)}
                {status_item("PDF ejecutivo", pdf_status)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_blocked_integrated_report_card(message, next_step_message):
    st.markdown(
        f"""
        <div class="blocked-action-card">
            <div class="blocked-action-title">Informe financiero integrado no disponible</div>
            <div class="blocked-action-text">{html.escape(message)}</div>
            <div class="executive-conclusion">
                <strong>Siguiente paso</strong>
                {html.escape(next_step_message)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(
    page_title="Dashboard Evolutivo Financiero Kappo",
    layout="wide",
)

apply_kappo_theme()

with st.sidebar:
    st.header("Carga de datos")
    uploaded_file = st.file_uploader("Excel Kame Estado Resultado", type=["xlsx", "xlsm", "xls"])
    uploaded_balance_file = st.file_uploader(
        "Balance Clasificado Kame",
        type=["xlsx", "xlsm", "xls"],
    )
    st.caption("El archivo se lee en memoria y no se modifica.")


has_eerr_file = uploaded_file is not None
has_balance_file = uploaded_balance_file is not None
integrated_report_ready = has_eerr_file and has_balance_file

if not has_eerr_file and not has_balance_file:
    render_header(
        "Bienvenido al Dashboard Financiero Kappo",
        "Carga el Estado de Resultados y el Balance Clasificado para generar un informe financiero integrado.",
        None,
    )
    st.markdown(
        """
        <div class="executive-card">
            <div class="executive-title">Antes de comenzar</div>
            <div class="executive-subtitle">
                Esta versión interna trabaja con ambos archivos para evitar informes parciales o mezclas de datos.
            </div>
            <div class="executive-conclusion">
                <strong>Flujo recomendado</strong>
                Carga primero el Estado de Resultados y luego el Balance Clasificado. Con ambos archivos se habilitan el análisis Kappo y el PDF ejecutivo.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_loading_status_card(
        has_eerr_file=False,
        has_balance_file=False,
        has_analysis=False,
    )
    st.stop()

if has_balance_file and not has_eerr_file:
    render_header(
        "Dashboard Evolutivo Financiero Kappo",
        "Validación básica de Balance Clasificado.",
        "Informe integrado bloqueado",
    )
    _render_loading_status_card(
        has_eerr_file=False,
        has_balance_file=True,
        has_analysis=False,
    )
    st.markdown(
        """
        <div class="executive-card">
            <div class="executive-title">Balance Clasificado cargado correctamente</div>
            <div class="executive-subtitle">Falta Estado de Resultados para generar informe financiero integrado.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    try:
        base_balance_normalizada, diagnostics_balance = load_kame_balance(uploaded_balance_file)
        balance_kpis = calculate_balance_kpis(base_balance_normalizada)
        control_balance = diagnostics_balance.get("control_balance", {})
        section_title("Balance Clasificado")
        bal_col1, bal_col2, bal_col3, bal_col4 = st.columns(4)
        bal_col1.metric("Razón corriente", _format_ratio(balance_kpis.get("razon_corriente")))
        bal_col2.metric("Capital de trabajo", format_clp(balance_kpis.get("capital_trabajo")))
        bal_col3.metric("Prueba ácida", _format_ratio(balance_kpis.get("prueba_acida")))
        bal_col4.metric(
            "Deuda corriente / patrimonio",
            _format_ratio(balance_kpis.get("deuda_corriente_sobre_patrimonio")),
        )
        with st.expander("Base_balance_normalizada y control", expanded=False):
            st.json(control_balance)
            st.dataframe(base_balance_normalizada, use_container_width=True, hide_index=True)
        section_title("Análisis Kappo")
        _render_blocked_integrated_report_card(
            "Balance Clasificado cargado correctamente. Falta Estado de Resultados para generar informe financiero integrado.",
            "Carga el Estado de Resultados para habilitar análisis Kappo y PDF ejecutivo.",
        )
        st.button("Solicitar análisis Kappo", disabled=True)
        st.caption("Carga el Estado de Resultados para habilitar análisis Kappo y PDF ejecutivo.")
    except Exception as exc:
        st.error(f"No se pudo normalizar el Balance Clasificado: {exc}")
    st.stop()

source = uploaded_file

nombre_archivo = getattr(source, "name", None)
if nombre_archivo is None:
    nombre_archivo = Path(source).name


try:
    base_normalizada, diagnostics = load_kame_eerr(source)
except Exception as exc:
    st.error(f"No se pudo normalizar el archivo: {exc}")
    st.stop()


base_balance_normalizada = pd.DataFrame()
diagnostics_balance = {}
balance_kpis = {}
if uploaded_balance_file is not None:
    try:
        base_balance_normalizada, diagnostics_balance = load_kame_balance(uploaded_balance_file)
        balance_kpis = calculate_balance_kpis(base_balance_normalizada)
    except Exception as exc:
        st.error(f"No se pudo normalizar el Balance Clasificado: {exc}")


source_key = _source_session_key(nombre_archivo, diagnostics)
_reset_adjustments_for_source(source_key)
balance_source_name = getattr(uploaded_balance_file, "name", "SIN_BALANCE")
ai_source_key = f"{source_key}|balance:{balance_source_name}"
if st.session_state.get("kappo_ai_source_key") != ai_source_key:
    st.session_state["kappo_ai_source_key"] = ai_source_key
    st.session_state.pop("kappo_ai_response", None)
    st.session_state.pop("kappo_ai_payload", None)
ajustes_usuario = st.session_state.setdefault("ajustes_usuario", [])
base_ajustada = apply_manual_adjustments(base_normalizada, ajustes_usuario)
control_ajustado = build_adjusted_control_cuadratura(base_ajustada)
resumen_control_ajustado = build_adjusted_control_summary(control_ajustado)
diagnostics_analisis = _build_adjusted_diagnostics(
    diagnostics,
    control_ajustado,
    resumen_control_ajustado,
    ajustes_usuario,
)
base_analisis = base_ajustada
resumen_control_original = diagnostics.get("resumen_control_cuadratura", {})
resumen_control = diagnostics_analisis.get("resumen_control_cuadratura", {})
control_status = f"Control cuadratura: {resumen_control.get('estado_general', 'N/D')}"
render_header(
    "Dashboard Evolutivo Financiero Kappo",
    f"Vista ejecutiva sobre {diagnostics_analisis.get('base_de_analisis')} desde Estado de Resultados Kame.",
    control_status,
)

_render_reconciliation_center(
    exceptions=diagnostics.get("exceptions", []),
    ajustes_usuario=ajustes_usuario,
    nombre_archivo=nombre_archivo,
    base_ajustada=base_ajustada,
    control_original=diagnostics.get("control_cuadratura", []),
    resumen_original=resumen_control_original,
    resumen_ajustado=resumen_control_ajustado,
)

if uploaded_balance_file is not None and not base_balance_normalizada.empty:
    control_balance = diagnostics_balance.get("control_balance", {})
    section_title("Balance Clasificado")
    balance_status = "OK" if control_balance.get("cuadra_balance") else "REVISAR"
    st.caption(
        f"Balance opcional cargado. Control balance: {balance_status}. "
        "Estos indicadores complementan el EERR para liquidez, solvencia y mirada crediticia."
    )
    bal_col1, bal_col2, bal_col3, bal_col4 = st.columns(4)
    bal_col1.metric("Razón corriente", _format_ratio(balance_kpis.get("razon_corriente")))
    bal_col2.metric("Capital de trabajo", format_clp(balance_kpis.get("capital_trabajo")))
    bal_col3.metric("Prueba ácida", _format_ratio(balance_kpis.get("prueba_acida")))
    bal_col4.metric(
        "Deuda corriente / patrimonio",
        _format_ratio(balance_kpis.get("deuda_corriente_sobre_patrimonio")),
    )
    bal_col5, bal_col6, bal_col7, bal_col8 = st.columns(4)
    bal_col5.metric("Disponible", format_clp(balance_kpis.get("disponible")))
    bal_col6.metric("Inventarios / activo corriente", _format_percent_from_ratio(balance_kpis.get("inventarios_sobre_activo_corriente")))
    bal_col7.metric("Cuentas por cobrar / activo corriente", _format_percent_from_ratio(balance_kpis.get("cuentas_por_cobrar_sobre_activo_corriente")))
    bal_col8.metric("Ajuste patrimonio + resultado", format_clp(balance_kpis.get("patrimonio_mas_resultado")))
    with st.expander("Base_balance_normalizada y control", expanded=False):
        st.json(control_balance)
        st.dataframe(base_balance_normalizada, use_container_width=True, hide_index=True)

kpis = calculate_financial_kpis(base_analisis)
last_kpis = latest_period_kpis(kpis)


section_title("Tipo de comparación")
comparison_type = st.selectbox(
    "Selecciona la base de comparación para tarjetas, lectura ejecutiva, alertas y rankings",
    options=list(COMPARISON_TYPES.keys()),
    format_func=lambda key: COMPARISON_TYPES.get(key, key),
)
comparison_context = _build_comparison_context_compatible(kpis, comparison_type)
comparison_values = _compare_kpis_compatible(kpis, comparison_context)
credit_kpis = calculate_credit_kpis(
    eerr_kpis=comparison_values.get("final", {}),
    balance_kpis=balance_kpis,
    comparison_context=comparison_context,
)
mayores_aumentos, mayores_disminuciones = _rank_account_movements_for_context_compatible(
    base_analisis, comparison_context, top_n=10
)
if comparison_context.get("available"):
    st.caption(
        f"{comparison_context['label']}: "
        f"{comparison_context['periodo_inicial']} vs {comparison_context['periodo_final']}"
    )
    lectura_ejecutiva = _generate_comparison_reading_compatible(comparison_values)
    alertas_financieras = _build_comparison_alerts(comparison_values)
else:
    st.warning(comparison_context.get("message", "Comparación no disponible."))
    lectura_ejecutiva = [comparison_context.get("message", "Comparación no disponible.")]
    alertas_financieras = pd.DataFrame(
        columns=["periodo", "severidad", "indicador", "alerta", "valor", "umbral", "detalle"]
    )


section_title("Resumen ejecutivo financiero")
if comparison_context.get("available"):
    _render_comparison_cards(comparison_values)
else:
    st.info("Selecciona una comparación disponible para ver tarjetas ejecutivas.")


_render_executive_reading_card(lectura_ejecutiva, comparison_context, comparison_values)

section_title("Alertas financieras")
_render_alert_cards(alertas_financieras)


section_title("Análisis Kappo")
if not integrated_report_ready:
    _render_blocked_integrated_report_card(
        "Estado de Resultados cargado correctamente. Falta Balance Clasificado para generar informe financiero integrado.",
        "Carga el Balance Clasificado para habilitar análisis Kappo y PDF ejecutivo.",
    )
    st.button("Solicitar análisis Kappo", disabled=True)
    st.caption("El análisis Kappo se habilita cuando Estado de Resultados y Balance Clasificado están cargados.")
else:
    st.markdown(
        """
        <div class="blocked-action-card">
            <div class="blocked-action-title">Análisis Kappo disponible</div>
            <div class="blocked-action-text">
                El informe integrado usará Estado de Resultados, Balance Clasificado, conciliación vigente e indicadores crediticios preliminares.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    enfoque_analisis = st.selectbox(
        "Enfoque del análisis Kappo",
        options=[
            "Ejecutivo general",
            "Variaciones principales",
            "Ingresos y margen",
            "Gastos y eficiencia",
            "Rentabilidad y resultado",
            "Riesgos financieros",
            "Mirada crediticia preliminar",
            "Análisis completo",
        ],
        index=0,
    )

    n8n_payload = build_n8n_payload(
        nombre_archivo=nombre_archivo,
        comparison_context=comparison_context,
        comparison_values=comparison_values,
        diagnostics=diagnostics_analisis,
        alertas_financieras=alertas_financieras,
        lectura_ejecutiva=lectura_ejecutiva,
        enfoque_analisis=enfoque_analisis,
        balance_kpis=balance_kpis,
        credit_kpis=credit_kpis,
        diagnostics_balance=diagnostics_balance,
    )

    if st.button("Solicitar análisis Kappo", type="primary"):
        try:
            status_code, response_body = _post_json_to_n8n(n8n_payload)
            st.info("Solicitud enviada. Revisa la ejecución en n8n.")
            st.write("Status code:", status_code)
            if response_body:
                parsed_response = _render_n8n_analysis(response_body)
                st.session_state["kappo_ai_response"] = parsed_response
                st.session_state["kappo_ai_payload"] = n8n_payload
                with st.expander("Respuesta técnica n8n", expanded=False):
                    if parsed_response:
                        st.json(parsed_response)
                    else:
                        st.code(response_body)
            else:
                st.caption("n8n no devolvió contenido en la respuesta.")
        except Exception as exc:
            st.error(f"No se pudo enviar la solicitud a n8n: {exc}")

    saved_ai_response = st.session_state.get("kappo_ai_response")
    saved_ai_payload = st.session_state.get("kappo_ai_payload", n8n_payload)
    if saved_ai_response:
        saved_ai_payload = {
            **saved_ai_payload,
            "balance_kpis": n8n_payload.get("balance_kpis", saved_ai_payload.get("balance_kpis", {})),
            "credit_kpis": {
                **(saved_ai_payload.get("credit_kpis") or {}),
                **(n8n_payload.get("credit_kpis") or {}),
            },
            "control_balance": n8n_payload.get("control_balance", saved_ai_payload.get("control_balance", {})),
        }
    if saved_ai_response and saved_ai_response.get("informe"):
        try:
            pdf_bytes = _build_ai_report_pdf_bytes(saved_ai_response, saved_ai_payload)
            st.download_button(
                "Descargar informe Kappo en PDF",
                data=pdf_bytes,
                file_name="informe_financiero_kappo_v2.pdf",
                mime="application/pdf",
            )
        except ImportError:
            st.warning("Instala reportlab para habilitar la descarga PDF del informe Kappo.")
        except Exception as exc:
            st.error(f"No se pudo generar el PDF del informe Kappo: {exc}")

    with st.expander("Payload enviado a n8n", expanded=False):
        st.json(n8n_payload)


with st.expander("Resumen fijo del último período", expanded=False):
    st.caption("Este bloque no depende del selector.")
    fixed_alerts = build_financial_alerts(kpis)
    if not last_kpis:
        st.info("No hay KPIs disponibles para mostrar.")
    else:
        last_period = last_kpis.get("periodo", "N/D")
        st.caption(f"Último período disponible: {last_period}")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric(
            "Ingresos explotación",
            format_clp(last_kpis.get("ingresos_explotacion")),
            delta=format_signed_clp(last_kpis.get("var_mom_ingresos")),
        )
        col2.metric("Margen explotación", format_clp(last_kpis.get("margen_explotacion")))
        col3.metric("Margen sobre ingresos", format_pct(last_kpis.get("margen_pct")))
        col4.metric(
            "Gastos adm. y ventas",
            format_clp(last_kpis.get("gastos_administracion_ventas")),
            delta=format_signed_clp(_expense_abs_delta(kpis, "gastos_administracion_ventas")),
            delta_color="inverse",
        )
        col5.metric(
            "Resultado final",
            format_clp(last_kpis.get("utilidad_perdida_ejercicio")),
            delta=format_signed_clp(last_kpis.get("var_mom_resultado_final")),
        )
        st.caption(
            f"Gastos financieros / bancarios del período: "
            f"{format_clp(last_kpis.get('gastos_financieros'))}"
        )
        if fixed_alerts.empty:
            st.success("Sin alertas financieras básicas para el último período.")
        else:
            _render_alert_cards(fixed_alerts)


section_title("Gráficos evolutivos")
if kpis.empty:
    st.info("No hay datos suficientes para graficar.")
elif st_echarts is None:
    st.warning("Instala streamlit-echarts para visualizar los gráficos simples.")
else:
    chart_col1, chart_col2 = st.columns([2, 1])
    with chart_col1:
        st_echarts(
            options=build_financial_line_options(kpis),
            height="360px",
            key="financial_line_chart",
        )
    with chart_col2:
        st_echarts(
            options=build_admin_expenses_bar_options(kpis),
            height="360px",
            key="admin_expenses_bar_chart",
        )


section_title("Histórico mensual completo")
if kpis.empty:
    st.info("No hay tabla evolutiva disponible.")
else:
    st.dataframe(format_kpis_table(kpis), use_container_width=True, hide_index=True)


section_title("Ranking de variación")
if comparison_context.get("available"):
    st.caption(
        f"{comparison_context['label']}: "
        f"{comparison_context['periodo_inicial']} vs {comparison_context['periodo_final']}"
    )
else:
    st.info("El ranking no está disponible para la comparación seleccionada.")
rank_col1, rank_col2 = st.columns(2, gap="large")
with rank_col1:
    _render_ranking_card("Mayores variaciones positivas", mayores_aumentos)

with rank_col2:
    _render_ranking_card("Mayores variaciones negativas", mayores_disminuciones)


section_title("Exportar análisis")
try:
    export_bytes = _build_export_workbook_compatible(
        base_normalizada=base_analisis,
        kpis=kpis,
        diagnostics=diagnostics_analisis,
        mayores_aumentos=mayores_aumentos,
        mayores_disminuciones=mayores_disminuciones,
        lectura_ejecutiva=lectura_ejecutiva,
        alertas_financieras=alertas_financieras,
    )
    st.download_button(
        "Descargar análisis financiero evolutivo",
        data=export_bytes,
        file_name="analisis_financiero_evolutivo_kappo.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
except Exception as exc:
    st.error(f"No se pudo generar el Excel de análisis: {exc}")


with st.expander("Control_cuadratura", expanded=False):
    cols_control = st.columns(5)
    cols_control[0].metric(
        "Grupos/período auditados",
        resumen_control.get("grupos_periodo_auditados", 0),
    )
    cols_control[1].metric("Controles OK", resumen_control.get("controles_ok", 0))
    cols_control[2].metric(
        "Con diferencia",
        resumen_control.get("controles_con_diferencia", 0),
    )
    cols_control[3].metric(
        "Mayor diferencia abs",
        format_clp(resumen_control.get("mayor_diferencia_abs", 0)),
    )
    cols_control[4].metric("Estado general", resumen_control.get("estado_general", "N/D"))

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Columna TOTAL ignorada", str(diagnostics_analisis.get("columna_total_ignorada", False)).upper())
    col_b.metric("Períodos detectados", len(diagnostics_analisis.get("periodos_detectados", [])))
    col_c.metric("Filas normalizadas", diagnostics_analisis.get("filas_base_normalizada", 0))

    st.write("Períodos:", ", ".join(diagnostics_analisis.get("periodos_detectados", [])))
    st.write("Cantidad de filas por nivel:", diagnostics_analisis.get("filas_base_por_nivel", {}))

    control_cuadratura = diagnostics_analisis.get("control_cuadratura", [])
    if control_cuadratura:
        st.dataframe(format_control_table(control_cuadratura), use_container_width=True, hide_index=True)
    else:
        st.info("No hay grupos con niveles detalle y total para cuadrar.")

    diferencias_a_revisar = [row for row in control_cuadratura if not row.get("cuadra")]
    st.markdown("#### Diferencias a revisar")
    if diferencias_a_revisar:
        st.dataframe(format_control_table(diferencias_a_revisar), use_container_width=True, hide_index=True)
    else:
        st.success("No hay diferencias de cuadratura.")

    detalle_negativos = diagnostics.get("detalle_montos_negativos_diferencias", [])
    if diferencias_a_revisar:
        st.markdown("#### Cuentas detalle con monto_origen negativo en diferencias")
        if detalle_negativos:
            st.dataframe(detalle_negativos, use_container_width=True, hide_index=True)
        else:
            st.info("No se detectaron cuentas detalle con monto_origen negativo en esos período/grupo.")

section_title("Resumen simple por período / grupo / nivel")
if base_analisis.empty:
    st.info("No hay filas normalizadas.")
else:
    resumen = (
        base_analisis.groupby(["periodo", "grupo", "nivel"], as_index=False)
        .agg(monto=("monto", "sum"), filas=("cuenta", "count"))
        .sort_values(["periodo", "grupo", "nivel"])
    )
    st.dataframe(format_group_summary_table(resumen), use_container_width=True, hide_index=True)


with st.expander("Base de analisis", expanded=False):
    required_cols = ["periodo", "grupo", "cuenta", "monto", "origen", "nivel", "orden", "fuente"]
    audit_cols = [
        col
        for col in ["fila_origen", "monto_origen", "signo_normalizado"]
        if col in base_analisis.columns
    ]
    st.dataframe(
        base_analisis[required_cols + audit_cols],
        use_container_width=True,
        hide_index=True,
    )


with st.expander("Diagnostics", expanded=False):
    st.json(json.loads(json.dumps(diagnostics_analisis, default=str)))

