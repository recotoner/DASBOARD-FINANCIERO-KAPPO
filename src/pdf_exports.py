from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any


PDF_VERSION_LABEL = "Versión ejecutiva"


def build_kappo_ai_report_pdf(
    *,
    informe: str,
    nombre_archivo: str,
    tipo_comparacion: str,
    periodo_base: str,
    periodo_actual: str,
    fuente_base: str,
    estado_cuadratura: str,
    ajustes_aplicados: int,
    salud_financiera: str | None = None,
    kpis: dict[str, Any] | None = None,
    balance_kpis: dict[str, Any] | None = None,
    credit_kpis: dict[str, Any] | None = None,
    control_balance: dict[str, Any] | None = None,
) -> bytes:
    """Build the visible V2 executive PDF for the Kappo agent report."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    generated_at = datetime.now().strftime("%d-%m-%Y %H:%M")
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.62 * inch,
        leftMargin=0.62 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.62 * inch,
        title="Informe Financiero Kappo V2",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CoverTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=25,
        leading=30,
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    cover_subtitle_style = ParagraphStyle(
        "CoverSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=16,
        textColor=colors.HexColor("#EAF5E3"),
        alignment=TA_CENTER,
    )
    version_style = ParagraphStyle(
        "CoverVersion",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#2F6B1F"),
        alignment=TA_CENTER,
    )
    section_style = ParagraphStyle(
        "KappoSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=colors.HexColor("#17324D"),
        spaceBefore=12,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "KappoBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        textColor=colors.HexColor("#1F2937"),
        alignment=TA_JUSTIFY,
        spaceAfter=8,
    )
    bullet_style = ParagraphStyle(
        "KappoBullet",
        parent=body_style,
        leftIndent=16,
        firstLineIndent=-10,
        alignment=TA_JUSTIFY,
    )
    muted_style = ParagraphStyle(
        "KappoMuted",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.7,
        leading=12,
        textColor=colors.HexColor("#647067"),
        alignment=TA_JUSTIFY,
    )

    story = [
        _cover_page(
            logo=_logo_image(width=260),
            version=Paragraph(PDF_VERSION_LABEL, version_style),
            title=Paragraph("Informe Financiero Evolutivo Kappo", title_style),
            subtitle=Paragraph(
                "Estado de Resultados, Balance Clasificado y Análisis Ejecutivo",
                cover_subtitle_style,
            ),
            metadata=[
                ["Archivo", _safe_text(nombre_archivo)],
                ["Comparación", _safe_text(tipo_comparacion)],
                ["Períodos", f"{_safe_text(periodo_base)} vs {_safe_text(periodo_actual)}"],
                ["Base de análisis", _safe_text(fuente_base)],
                ["Fecha", generated_at],
            ],
        ),
        PageBreak(),
        _section_banner("Informe gerencial integrado"),
        Spacer(1, 10),
        Paragraph("Resumen ejecutivo del informe", section_style),
        _summary_cards(
            [
                ("Fuente base", _safe_text(fuente_base)),
                ("Control EERR", _safe_text(estado_cuadratura)),
                ("Ajustes aplicados", str(ajustes_aplicados)),
                ("Balance", _balance_status(control_balance)),
            ]
        ),
    ]

    if _has_meaningful_value(salud_financiera):
        story.append(Spacer(1, 8))
        story.append(_highlight_box(f"Salud financiera: {salud_financiera}"))

    story.extend(
        [
            Spacer(1, 8),
            Paragraph("Trazabilidad", section_style),
            _executive_trace_block(
                fuente_base=fuente_base,
                estado_cuadratura=estado_cuadratura,
                ajustes_aplicados=ajustes_aplicados,
                control_balance=control_balance,
                generated_at=generated_at,
            ),
            Spacer(1, 6),
            Paragraph(
                "El informe se genera sobre la base vigente en la app. Si existen ajustes de conciliación "
                "aplicados por el usuario, el análisis y la respuesta del agente usan Base_ajustada.",
                muted_style,
            ),
        ]
    )

    if kpis:
        story.extend(
            [
                Paragraph("Estado de Resultados Evolutivo", section_style),
                _kpi_table(_eerr_kpi_rows(kpis)),
            ]
        )

    if balance_kpis:
        story.extend(
            [
                _section_banner("Balance Clasificado"),
                Spacer(1, 8),
                _kpi_table(_balance_kpi_rows(balance_kpis, control_balance)),
            ]
        )

    if credit_kpis:
        story.extend(
            [
                _section_banner("Indicadores crediticios preliminares"),
                Spacer(1, 8),
                Paragraph("Rentabilidad", section_style),
                _kpi_table(_credit_profitability_rows(credit_kpis)),
                Paragraph("Liquidez y capital de trabajo", section_style),
                _kpi_table(_credit_liquidity_rows(credit_kpis)),
                Paragraph("Endeudamiento y solvencia", section_style),
                _kpi_table(_credit_solvency_rows(credit_kpis, balance_kpis)),
                Paragraph("Limitaciones del análisis", section_style),
                _kpi_table(_credit_limitations_rows(credit_kpis)),
            ]
        )

    story.extend(
        [
            _section_banner("Análisis Kappo"),
            Spacer(1, 8),
        ]
    )
    story.extend(_analysis_box(_report_paragraphs(_normalize_report_text(informe), section_style, body_style, bullet_style)))

    doc.build(story, onFirstPage=_draw_cover_frame, onLaterPages=_draw_page_frame)
    buffer.seek(0)
    return buffer.getvalue()


def _logo_path() -> Path:
    return Path(__file__).resolve().parent.parent / "Logo-Kappo-gestion-y-consultoria.png"


def _logo_image(width: int = 220):
    from reportlab.platypus import Image

    logo_path = _logo_path()
    if not logo_path.exists():
        return None
    logo = Image(str(logo_path))
    logo.drawWidth = width
    logo.drawHeight = logo.drawWidth * logo.imageHeight / logo.imageWidth
    return logo


def _cover_page(*, logo, version, title, subtitle, metadata: list[list[str]]):
    from reportlab.lib import colors
    from reportlab.platypus import Spacer, Table, TableStyle

    logo_cell = logo if logo else _logo_fallback()
    metadata_table = _cover_metadata_table(metadata)
    table = Table(
        [[logo_cell], [version], [title], [subtitle], [metadata_table]],
        colWidths=[505],
        rowHeights=[78, 34, 58, 50, 170],
        hAlign="CENTER",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.white),
                ("BACKGROUND", (0, 1), (0, 1), colors.HexColor("#E8F4DC")),
                ("BACKGROUND", (0, 2), (0, 3), colors.HexColor("#2F6B1F")),
                ("BACKGROUND", (0, 4), (0, 4), colors.HexColor("#F5F8F2")),
                ("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor("#BFD8B5")),
                ("LEFTPADDING", (0, 0), (-1, -1), 26),
                ("RIGHTPADDING", (0, 0), (-1, -1), 26),
                ("TOPPADDING", (0, 0), (0, 0), 18),
                ("BOTTOMPADDING", (0, 0), (0, 0), 10),
                ("TOPPADDING", (0, 1), (0, 1), 10),
                ("BOTTOMPADDING", (0, 1), (0, 1), 10),
                ("TOPPADDING", (0, 2), (0, 2), 18),
                ("BOTTOMPADDING", (0, 2), (0, 2), 4),
                ("TOPPADDING", (0, 3), (0, 3), 2),
                ("BOTTOMPADDING", (0, 3), (0, 3), 20),
                ("TOPPADDING", (0, 4), (0, 4), 22),
                ("BOTTOMPADDING", (0, 4), (0, 4), 22),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return table


def _logo_fallback():
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph

    style = ParagraphStyle(
        "LogoFallback",
        fontName="Helvetica-Bold",
        fontSize=28,
        leading=32,
        textColor=colors.HexColor("#2F6B1F"),
        alignment=TA_CENTER,
    )
    return Paragraph("KAPPO", style)


def _section_banner(text: str):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    style = ParagraphStyle(
        "SectionBanner",
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    table = Table([[Paragraph(_escape(text), style)]], colWidths=[505], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#2F6B1F")),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return table


def _executive_trace_block(*, fuente_base, estado_cuadratura, ajustes_aplicados, control_balance, generated_at):
    return _summary_cards(
        [
            ("Base", _safe_text(fuente_base)),
            ("Control EERR", _safe_text(estado_cuadratura)),
            ("Ajustes", str(ajustes_aplicados)),
            ("Balance", _balance_status(control_balance)),
        ]
    )


def _cover_metadata_table(rows: list[list[str]]):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    label = ParagraphStyle("CoverLabel", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=colors.HexColor("#244A1D"), alignment=TA_LEFT)
    value = ParagraphStyle("CoverValue", fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#1F2937"), alignment=TA_LEFT)
    prepared = [[Paragraph(_escape(a), label), Paragraph(_escape(b), value)] for a, b in rows]
    table = Table(prepared, colWidths=[135, 260], hAlign="CENTER")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8F4DC")),
                ("BACKGROUND", (1, 0), (1, -1), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D9E2D3")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _summary_cards(items: list[tuple[str, str]]):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    label = ParagraphStyle("CardLabel", fontName="Helvetica-Bold", fontSize=7.8, leading=10, textColor=colors.HexColor("#5F6B5A"), alignment=TA_CENTER)
    value = ParagraphStyle("CardValue", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=colors.HexColor("#12330F"), alignment=TA_CENTER)
    cells = [[Paragraph(_escape(name), label), Paragraph(_escape(val), value)] for name, val in items]
    table = Table([cells], colWidths=[126, 126, 126, 126], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7FAF5")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9E2D3")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D9E2D3")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return table


def _highlight_box(text: str):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    style = ParagraphStyle("Highlight", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=colors.HexColor("#2F6B1F"), alignment=TA_CENTER)
    table = Table([[Paragraph(_escape(text), style)]], colWidths=[505], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E8F4DC")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#C9E1B8")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _metadata_table(rows: list[list[str]]):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    label_style = ParagraphStyle("MetadataLabel", fontName="Helvetica-Bold", fontSize=8.8, leading=11, textColor=colors.HexColor("#244A1D"), alignment=TA_LEFT)
    value_style = ParagraphStyle("MetadataValue", fontName="Helvetica", fontSize=8.8, leading=11, textColor=colors.HexColor("#1F2937"), alignment=TA_LEFT)
    prepared_rows = [[Paragraph(_escape(str(label)), label_style), Paragraph(_escape(str(value)), value_style)] for label, value in rows]
    table = Table(prepared_rows, colWidths=[150, 355], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8F4DC")),
                ("BACKGROUND", (1, 0), (1, -1), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D9E2D3")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _kpi_table(rows: list[list[str]]):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    header_style = ParagraphStyle("KpiHeader", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.white, alignment=TA_LEFT)
    cell_style = ParagraphStyle("KpiCell", fontName="Helvetica", fontSize=8.6, leading=11, textColor=colors.HexColor("#1F2937"), alignment=TA_LEFT)
    prepared_rows = [[Paragraph("Indicador", header_style), Paragraph("Valor", header_style), Paragraph("Lectura", header_style)]]
    prepared_rows.extend(
        [
            Paragraph(_escape(str(label)), cell_style),
            Paragraph(_escape(str(value)), cell_style),
            Paragraph(_escape(str(note)), cell_style),
        ]
        for label, value, note in rows
    )
    table = Table(prepared_rows, colWidths=[180, 120, 205], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F6B1F")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAF5")]),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D9E2D3")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _analysis_box(elements):
    from reportlab.platypus import Spacer

    return [*elements, Spacer(1, 4)]


def _eerr_kpi_rows(kpis: dict[str, Any]) -> list[list[str]]:
    base = kpis.get("base", {}) or {}
    actual = kpis.get("actual", {}) or {}
    variation = kpis.get("variacion", {}) or {}
    return [
        ["Ingresos actual", _format_money(actual.get("ingresos_explotacion")), "Nivel de ingresos del período actual."],
        ["Margen explotación actual", _format_money(actual.get("margen_explotacion")), "Margen operacional antes de gastos no directos."],
        ["Resultado final actual", _format_money(actual.get("utilidad_perdida_ejercicio")), "Resultado final usado por el agente."],
        ["Variación ingresos", _format_money(variation.get("ingresos_explotacion")), "Cambio respecto a la base comparativa."],
        ["Variación resultado final", _format_money(variation.get("utilidad_perdida_ejercicio")), "Impacto final de la comparación seleccionada."],
        ["Ingresos base", _format_money(base.get("ingresos_explotacion")), "Base usada para comparar."],
    ]


def _balance_kpi_rows(balance_kpis: dict[str, Any], control_balance: dict[str, Any] | None) -> list[list[str]]:
    return [
        ["Control balance", _balance_status(control_balance), "Cuadratura entre activos, pasivos, patrimonio y resultado."],
        ["Activo total", _format_money(balance_kpis.get("activo_total")), "Tamaño financiero total observado."],
        ["Activo corriente", _format_money(balance_kpis.get("activo_corriente")), "Base de liquidez operacional."],
        ["Pasivo corriente", _format_money(balance_kpis.get("pasivo_corriente")), "Obligaciones de corto plazo."],
        ["Capital de trabajo", _format_money(balance_kpis.get("capital_trabajo")), "Activo corriente menos pasivo corriente."],
        ["Razón corriente", _format_ratio(balance_kpis.get("razon_corriente")), "Capacidad de cubrir pasivos corrientes."],
        ["Prueba ácida", _format_ratio(balance_kpis.get("prueba_acida")), "Liquidez sin considerar inventarios."],
        ["Patrimonio + resultado", _format_money(balance_kpis.get("patrimonio_mas_resultado")), "Base patrimonial ajustada por resultado."],
    ]


def _credit_profitability_rows(credit_kpis: dict[str, Any]) -> list[list[str]]:
    return [
        ["Margen operacional", _format_pct_ratio(credit_kpis.get("margen_operacional")), "Resultado operacional sobre ingresos."],
        ["Margen neto", _format_pct_ratio(credit_kpis.get("margen_neto")), "Resultado final sobre ingresos."],
        ["Gastos financieros / ingresos", _format_pct_ratio(credit_kpis.get("gastos_financieros_sobre_ingresos")), "Peso de la carga financiera sobre ingresos."],
        ["Resultado final negativo", _format_bool(credit_kpis.get("resultado_final_negativo")), "Alerta preliminar de rentabilidad."],
    ]


def _credit_liquidity_rows(credit_kpis: dict[str, Any]) -> list[list[str]]:
    return [
        ["Capital de trabajo / ingresos", _format_pct_ratio(credit_kpis.get("capital_trabajo_sobre_ingresos")), "Relación entre holgura operacional e ingresos."],
        ["Disponible / pasivo corriente", _format_pct_ratio(credit_kpis.get("disponible_sobre_pasivo_corriente")), "Caja disponible frente a obligaciones corrientes."],
        ["Capital de trabajo negativo", _format_bool(credit_kpis.get("capital_trabajo_negativo")), "Alerta de presión de corto plazo."],
        ["Liquidez estrecha", _format_bool(credit_kpis.get("liquidez_estrecha")), "Indica prueba ácida menor a 1."],
    ]


def _credit_solvency_rows(credit_kpis: dict[str, Any]) -> list[list[str]]:
    return [
        ["Pasivo corriente / activo total", _format_pct_ratio(credit_kpis.get("pasivo_corriente_sobre_activo_total")), "Peso de obligaciones corrientes sobre activos."],
        ["Patrimonio + resultado / activo total", _format_pct_ratio(credit_kpis.get("patrimonio_mas_resultado_sobre_activo_total")), "Base patrimonial ajustada sobre activos."],
        ["Deuda corriente / patrimonio", _format_ratio(credit_kpis.get("deuda_corriente_sobre_patrimonio")), "Apalancamiento corriente preliminar."],
        ["Obligaciones bancarias CP / pasivo corriente", _format_pct_ratio(credit_kpis.get("obligaciones_bancarias_cp_sobre_pasivo_corriente")), "Concentración bancaria de corto plazo."],
    ]


def _credit_limitations_rows(credit_kpis: dict[str, Any]) -> list[list[str]]:
    return [
        ["EBITDA disponible", _format_bool(credit_kpis.get("ebitda_disponible")), "No se calcula EBITDA real en esta versión."],
        ["Motivo", _safe_text(credit_kpis.get("motivo_ebitda_no_disponible")), "Limitación metodológica del análisis preliminar."],
    ]


def _report_paragraphs(report: str, section_style, body_style, bullet_style):
    from reportlab.platypus import Paragraph

    elements = []
    lines = str(report or "").replace("\r\n", "\n").split("\n")
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        normalized = line.rstrip(":").strip().lower()
        if _is_section_heading(normalized, line):
            elements.append(Paragraph(_escape(line.rstrip(":")), section_style))
        elif line.startswith(("-", "*", "•", "â€¢")):
            clean = line.lstrip("-*•â€¢ ").strip()
            elements.append(Paragraph(f"- {_escape(clean)}", bullet_style))
        else:
            elements.append(Paragraph(_escape(line), body_style))
    if not elements:
        elements.append(Paragraph("Sin informe disponible.", body_style))
    return elements


def _is_section_heading(normalized: str, original: str) -> bool:
    known = {
        "resumen ejecutivo",
        "puntos relevantes",
        "alertas o riesgos",
        "alertas",
        "riesgos",
        "recomendacion",
        "recomendaciones",
        "diagnostico",
        "analisis",
    }
    return normalized in known or (original.endswith(":") and len(original) <= 80)


def _normalize_report_text(report: str) -> str:
    return (
        str(report or "")
        .replace("days sales outstanding", "días promedio de cobranza")
        .replace("Days Sales Outstanding", "días promedio de cobranza")
        .replace("Analisis", "Análisis")
        .replace("analisis", "análisis")
        .replace("Comparacion", "Comparación")
        .replace("comparacion", "comparación")
        .replace("Periodos", "Períodos")
        .replace("periodos", "períodos")
        .replace("Razon", "Razón")
        .replace("razon", "razón")
    )


def _balance_status(control_balance: dict[str, Any] | None) -> str:
    if not control_balance:
        return "No cargado"
    return "OK" if control_balance.get("cuadra_balance") else "REVISAR"


def _has_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return bool(text) and text.lower() not in {"n/d", "nd", "none", "null", "nan", "-"}


def _format_money(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/D"
    sign = "-" if number < 0 else ""
    return f"{sign}${abs(number):,.0f}".replace(",", ".")


def _format_ratio(value: Any) -> str:
    try:
        return f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "N/D"


def _format_pct_ratio(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/D"
    if number != number:
        return "N/D"
    return f"{number * 100:,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def _format_bool(value: Any) -> str:
    if value is True:
        return "Sí"
    if value is False:
        return "No"
    return "N/D"


def _balance_kpi_rows(balance_kpis: dict[str, Any], control_balance: dict[str, Any] | None) -> list[list[str]]:
    return [
        ["Control balance", _balance_status(control_balance), "Cuadratura entre activos, pasivos, patrimonio y resultado."],
        ["Activo total", _format_money(balance_kpis.get("activo_total")), "Tamaño financiero total observado."],
        ["Activo corriente", _format_money(balance_kpis.get("activo_corriente")), "Base de liquidez operacional."],
        ["Pasivo corriente", _format_money(balance_kpis.get("pasivo_corriente")), "Obligaciones de corto plazo."],
        ["Capital de trabajo", _format_money(balance_kpis.get("capital_trabajo")), "Activo corriente menos pasivo corriente."],
        ["Razón corriente", _format_ratio(balance_kpis.get("razon_corriente")), "Capacidad de cubrir pasivos corrientes."],
        ["Prueba ácida", _format_ratio(balance_kpis.get("prueba_acida")), "Liquidez sin considerar inventarios."],
        ["Patrimonio contable", _format_money(balance_kpis.get("patrimonio_contable", balance_kpis.get("patrimonio"))), "Patrimonio informado por Balance."],
        ["Resultado del ejercicio", _format_money(balance_kpis.get("resultado_ejercicio")), "Resultado incorporado al bloque patrimonial."],
        ["Patrimonio ajustado por resultado", _format_money(balance_kpis.get("patrimonio_ajustado_por_resultado", balance_kpis.get("patrimonio_mas_resultado"))), "Patrimonio contable más resultado del ejercicio."],
    ]


def _credit_profitability_rows(credit_kpis: dict[str, Any]) -> list[list[str]]:
    return [
        ["Margen operacional", _format_pct_ratio(credit_kpis.get("margen_operacional")), "Resultado operacional sobre ingresos."],
        ["Margen neto", _format_pct_ratio(credit_kpis.get("margen_neto")), "Resultado final sobre ingresos."],
        ["Gastos financieros/bancarios / ingresos", _format_pct_ratio(credit_kpis.get("gastos_financieros_bancarios_sobre_ingresos", credit_kpis.get("gastos_financieros_sobre_ingresos"))), "Peso de gastos financieros y bancarios clasificados en EERR."],
        ["Resultado final negativo", _format_bool(credit_kpis.get("resultado_final_negativo")), "Alerta preliminar de rentabilidad."],
    ]


def _credit_solvency_rows(
    credit_kpis: dict[str, Any], balance_kpis: dict[str, Any] | None = None
) -> list[list[str]]:
    balance = balance_kpis or {}
    activo_total = _first_number(credit_kpis.get("activo_total"), balance.get("activo_total"))
    patrimonio_contable = _first_number(
        credit_kpis.get("patrimonio_contable"),
        balance.get("patrimonio_contable"),
        balance.get("patrimonio"),
    )
    patrimonio_ajustado = _first_number(
        credit_kpis.get("patrimonio_ajustado_por_resultado"),
        balance.get("patrimonio_ajustado_por_resultado"),
        balance.get("patrimonio_mas_resultado"),
    )
    pasivo_corriente = _first_number(
        credit_kpis.get("pasivo_corriente"), balance.get("pasivo_corriente")
    )
    patrimonio_contable_sobre_activo_total = _first_number(
        credit_kpis.get("patrimonio_contable_sobre_activo_total"),
        _safe_ratio(patrimonio_contable, activo_total),
    )
    deuda_corriente_sobre_patrimonio_ajustado = _first_number(
        credit_kpis.get("deuda_corriente_sobre_patrimonio_ajustado"),
        balance.get("deuda_corriente_sobre_patrimonio_ajustado"),
        _safe_ratio(pasivo_corriente, patrimonio_ajustado),
    )
    return [
        ["Pasivo corriente / activo total", _format_pct_ratio(credit_kpis.get("pasivo_corriente_sobre_activo_total")), "Peso de obligaciones corrientes sobre activos."],
        ["Patrimonio contable / activo total", _format_pct_ratio(patrimonio_contable_sobre_activo_total), "Patrimonio informado sobre activos."],
        ["Patrimonio ajustado / activo total", _format_pct_ratio(credit_kpis.get("patrimonio_ajustado_sobre_activo_total", credit_kpis.get("patrimonio_mas_resultado_sobre_activo_total"))), "Patrimonio contable más resultado sobre activos."],
        ["Deuda corriente / patrimonio contable", _format_ratio(credit_kpis.get("deuda_corriente_sobre_patrimonio_contable", credit_kpis.get("deuda_corriente_sobre_patrimonio"))), "Apalancamiento sobre patrimonio informado."],
        ["Deuda corriente / patrimonio ajustado", _format_ratio(deuda_corriente_sobre_patrimonio_ajustado), "Apalancamiento sobre patrimonio ajustado por resultado."],
        ["Obligaciones bancarias CP / pasivo corriente", _format_pct_ratio(credit_kpis.get("obligaciones_bancarias_cp_sobre_pasivo_corriente")), "Concentración bancaria de corto plazo."],
    ]


def _first_number(*values: Any) -> float | None:
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number == number:
            return number
    return None


def _safe_ratio(num: Any, den: Any) -> float | None:
    try:
        numerator = float(num)
        denominator = float(den)
    except (TypeError, ValueError):
        return None
    if numerator != numerator or denominator != denominator or denominator == 0:
        return None
    return numerator / denominator


def _safe_text(value: Any) -> str:
    return str(value) if value not in (None, "") else "N/D"


def _escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _draw_cover_frame(canvas, doc):
    from reportlab.lib import colors

    canvas.saveState()
    width, height = doc.pagesize
    canvas.setFillColor(colors.HexColor("#2F6B1F"))
    canvas.rect(0, height - 18, width, 18, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#17324D"))
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(width / 2, 24, "Kappo Consultoría & Gestión a Empresas")
    canvas.restoreState()


def _draw_page_frame(canvas, doc):
    from reportlab.lib import colors

    canvas.saveState()
    width, height = doc.pagesize
    canvas.setFillColor(colors.HexColor("#2F6B1F"))
    canvas.rect(0, height - 20, width, 20, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(doc.leftMargin, height - 14, "Informe Financiero Evolutivo Kappo")
    canvas.setFillColor(colors.HexColor("#17324D"))
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(doc.leftMargin, 24, "Dashboard Evolutivo Financiero Kappo")
    canvas.drawRightString(width - doc.rightMargin, 24, f"Página {doc.page}")
    canvas.restoreState()
