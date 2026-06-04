from __future__ import annotations

import html

import streamlit as st


KAPPO_CSS = """
<style>
    #MainMenu { visibility: hidden; }
    header[data-testid="stHeader"] { background: transparent; }
    footer[data-testid="stFooter"] { visibility: hidden; }

    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at top left, rgba(232, 244, 220, 0.75), transparent 32rem),
            #f6f8f5;
    }
    .main .block-container {
        padding-top: 1.55rem;
        padding-bottom: 2rem;
        max-width: 1360px;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #343a40 0%, #2b3035 100%);
        border-right: 1px solid #23272b;
    }
    [data-testid="stSidebar"] * {
        color: #ecf0f1 !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploader"] section {
        background: rgba(0, 0, 0, 0.22) !important;
        border: 1px dashed rgba(255, 255, 255, 0.38) !important;
        border-radius: 8px !important;
    }
    [data-testid="stSidebar"] button {
        background: #495057 !important;
        color: #ffffff !important;
        border: 1px solid #6c757d !important;
    }

    .kappo-banner {
        background: linear-gradient(135deg, #2d5016 0%, #4a7c2a 100%);
        color: white;
        padding: 2.15rem 2.35rem;
        border-radius: 16px;
        margin-bottom: 1.55rem;
        box-shadow: 0 20px 38px rgba(30, 55, 18, 0.26);
        border-bottom: 5px solid rgba(232, 244, 220, 0.85);
    }
    .kappo-banner h1 {
        color: white !important;
        margin: 0;
        font-size: 2.05rem;
        font-weight: 850;
        letter-spacing: 0;
    }
    .kappo-banner p {
        margin: 0.65rem 0 0 0;
        opacity: 0.92;
        font-size: 1.02rem;
    }
    .section-title {
        color: #2c3e50;
        font-size: 1.28rem;
        font-weight: 750;
        margin: 1.65rem 0 0.75rem 0;
        padding-bottom: 0.35rem;
        border-bottom: 2px solid #4a7c2a;
    }
    .section-helper {
        color: #647067;
        font-size: 0.92rem;
        margin: -0.35rem 0 0.95rem 0;
        line-height: 1.38;
    }
    .status-pill {
        display: inline-block;
        padding: 0.25rem 0.7rem;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 700;
        background: #e8f4dc;
        color: #2d5016;
        border: 1px solid #c8e0a0;
        margin-left: 0.35rem;
    }
    [data-testid="stMetricContainer"] {
        background: linear-gradient(135deg, #ffffff 0%, #f6faf4 100%);
        padding: 1rem;
        border-radius: 12px;
        box-shadow: 0 10px 22px rgba(31, 41, 51, 0.07);
        border: 1px solid #d9e9cd;
        border-left: 5px solid #4a7c2a;
    }
    [data-testid="stMetricLabel"] {
        font-weight: 700;
        color: #2c3e50;
    }
    [data-testid="stMetricValue"] {
        color: #1f3a0f;
        font-weight: 800;
        letter-spacing: 0;
    }
    [data-testid="stSelectbox"] {
        background: #ffffff;
        border: 1px solid #dde8d5;
        border-radius: 12px;
        padding: 0.45rem 0.6rem 0.65rem 0.6rem;
        box-shadow: 0 8px 18px rgba(31, 41, 51, 0.05);
    }
    .stButton > button {
        border-radius: 8px;
        font-weight: 750;
        border: none !important;
        padding: 0.55rem 1rem;
        box-shadow: 0 6px 14px rgba(45, 80, 22, 0.14);
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #2d5016 0%, #4a7c2a 100%) !important;
        color: white !important;
    }
    .stButton > button:disabled {
        background: #dfe6dc !important;
        color: #7a8676 !important;
        border: 1px solid #cbd8c6 !important;
        box-shadow: none !important;
    }
    [data-testid="stDataFrame"] {
        border: 1px solid #dbe7d4;
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 8px 18px rgba(31, 41, 51, 0.05);
    }
    .comparison-card {
        background: linear-gradient(180deg, #ffffff 0%, #fbfdf9 100%);
        border: 1px solid #d8e7cf;
        border-left: 6px solid #4a7c2a;
        border-radius: 14px;
        padding: 1.15rem 1.2rem;
        min-height: 252px;
        box-shadow: 0 14px 28px rgba(31, 41, 51, 0.09);
        margin-bottom: 1.15rem;
        overflow: visible;
    }
    .comparison-card-title {
        color: #203047;
        font-size: 1.08rem;
        font-weight: 850;
        margin-bottom: 0.95rem;
        line-height: 1.25;
    }
    .comparison-period-block {
        display: grid;
        grid-template-columns: 1fr;
        gap: 0.35rem;
        background: #f5f9f2;
        border: 1px solid #dfebd8;
        border-radius: 10px;
        padding: 0.72rem 0.8rem;
        margin-bottom: 0.65rem;
    }
    .comparison-period-line {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 0.55rem;
        min-width: 0;
    }
    .comparison-period-label {
        color: #6c757d;
        font-size: 0.76rem;
        font-weight: 750;
        text-transform: uppercase;
        flex: 0 0 auto;
    }
    .comparison-period {
        color: #2c3e50;
        font-size: 0.86rem;
        font-weight: 800;
        line-height: 1.2;
        text-align: right;
        white-space: nowrap;
        overflow: visible;
    }
    .comparison-main-value {
        color: #1f3a0f;
        font-size: 1.32rem;
        font-weight: 900;
        line-height: 1.2;
        word-break: keep-all;
        overflow-wrap: normal;
        white-space: nowrap;
    }
    .comparison-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        border-top: 1px solid #e7edf3;
        padding-top: 0.62rem;
        margin-top: 0.62rem;
        font-size: 0.88rem;
        min-width: 0;
    }
    .comparison-label {
        color: #5f6f7f;
        font-weight: 760;
        flex: 0 0 auto;
    }
    .comparison-value {
        color: #1f2933;
        font-weight: 850;
        text-align: right;
        white-space: nowrap;
        overflow: visible;
    }
    .comparison-delta-positive {
        color: #2d5016;
    }
    .comparison-delta-negative {
        color: #b42318;
    }
    .comparison-delta-neutral {
        color: #495057;
    }
    .executive-card,
    .ranking-card {
        background: #ffffff;
        border: 1px solid #dde5ee;
        border-radius: 12px;
        box-shadow: 0 14px 28px rgba(31, 41, 51, 0.08);
        padding: 1.25rem 1.35rem;
        margin-bottom: 1.25rem;
    }
    .executive-card {
        background: linear-gradient(180deg, #ffffff 0%, #f9fcf7 100%);
        border-left: 6px solid #4a7c2a;
    }
    .executive-title,
    .ranking-title {
        color: #203047;
        font-size: 1.2rem;
        font-weight: 850;
        margin-bottom: 0.25rem;
    }
    .executive-subtitle,
    .ranking-subtitle {
        color: #657487;
        font-size: 0.94rem;
        font-weight: 650;
        margin-bottom: 0.95rem;
    }
    .load-status-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 0.85rem;
        margin-top: 0.35rem;
    }
    .load-status-item {
        background: #f7fbf3;
        border: 1px solid #d9e9cd;
        border-radius: 10px;
        padding: 0.9rem 1rem;
    }
    .load-status-label {
        color: #203047;
        font-weight: 850;
        margin-bottom: 0.25rem;
    }
    .load-status-value {
        color: #657487;
        font-size: 0.9rem;
        font-weight: 720;
    }
    .load-status-icon {
        display: inline-flex;
        width: 1.25rem;
        height: 1.25rem;
        align-items: center;
        justify-content: center;
        border-radius: 999px;
        margin-right: 0.4rem;
        font-weight: 900;
        font-size: 0.8rem;
    }
    .load-status-ok {
        background: #e8f4dc;
        color: #2d5016;
    }
    .load-status-pending {
        background: #fff4d6;
        color: #7a5600;
    }
    .load-status-locked {
        background: #e9eef4;
        color: #516170;
    }
    .blocked-action-card {
        background: #f7fbf3;
        border: 1px solid #d6e9c8;
        border-left: 6px solid #4a7c2a;
        border-radius: 12px;
        padding: 1.2rem 1.3rem;
        box-shadow: 0 10px 22px rgba(31, 41, 51, 0.07);
        margin-bottom: 0.9rem;
    }
    .blocked-action-title {
        color: #203047;
        font-size: 1.15rem;
        font-weight: 850;
        margin-bottom: 0.35rem;
    }
    .blocked-action-text {
        color: #556575;
        line-height: 1.42;
        margin-bottom: 0.85rem;
    }
    .insight-list {
        display: grid;
        gap: 0.55rem;
        margin: 0.2rem 0 1rem 0;
        padding: 0;
    }
    .insight-item {
        display: grid;
        grid-template-columns: 0.7rem 1fr;
        gap: 0.55rem;
        align-items: start;
        color: #1f2933;
        line-height: 1.38;
        font-size: 0.96rem;
    }
    .insight-dot {
        width: 0.45rem;
        height: 0.45rem;
        border-radius: 999px;
        background: #4a7c2a;
        margin-top: 0.42rem;
    }
    .executive-conclusion {
        background: #edf7e7;
        border: 1px solid #d6e9c8;
        border-radius: 8px;
        padding: 0.9rem 1rem;
        color: #244414;
        line-height: 1.35;
    }
    .executive-conclusion strong {
        display: block;
        margin-bottom: 0.2rem;
    }
    .alerts-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 0.85rem;
        margin-bottom: 1rem;
    }
    .alert-card {
        border-radius: 8px;
        border: 1px solid #dde5ee;
        padding: 0.95rem 1rem;
        box-shadow: 0 5px 14px rgba(31, 41, 51, 0.06);
    }
    .alert-card-high {
        background: #fff5f5;
        border-color: #f3c2c2;
    }
    .alert-card-medium {
        background: #fff9e8;
        border-color: #ead79a;
    }
    .alert-card-low,
    .alert-card-ok {
        background: #f3f7fb;
        border-color: #d9e4ef;
    }
    .alert-badge {
        display: inline-block;
        border-radius: 999px;
        padding: 0.18rem 0.55rem;
        font-size: 0.74rem;
        font-weight: 850;
        margin-bottom: 0.55rem;
    }
    .alert-badge-high {
        background: #fde7e7;
        color: #9f1d1d;
    }
    .alert-badge-medium {
        background: #fff0bd;
        color: #735000;
    }
    .alert-badge-low,
    .alert-badge-ok {
        background: #e7eef7;
        color: #41566d;
    }
    .alert-heading {
        color: #203047;
        font-weight: 850;
        margin-bottom: 0.25rem;
    }
    .alert-meta {
        color: #5f6f7f;
        font-size: 0.86rem;
        margin-bottom: 0.45rem;
    }
    .alert-detail {
        color: #1f2933;
        line-height: 1.35;
        font-size: 0.92rem;
    }
    .alert-ok-box {
        background: #eef6e9;
        border: 1px solid #cfe5bf;
        color: #244414;
        border-radius: 12px;
        padding: 1rem 1.1rem;
        box-shadow: 0 5px 14px rgba(31, 41, 51, 0.05);
        font-weight: 720;
        margin-bottom: 1rem;
    }
    .ai-analysis-card {
        background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
        border: 1px solid #d8e7cf;
        border-left: 6px solid #4a7c2a;
        border-radius: 14px;
        padding: 1.25rem 1.35rem;
        box-shadow: 0 14px 28px rgba(31, 41, 51, 0.08);
        margin: 0.8rem 0 1rem 0;
    }
    .ai-analysis-title {
        color: #203047;
        font-size: 1.08rem;
        font-weight: 850;
        margin-bottom: 0.45rem;
    }
    .ai-health-badge {
        display: inline-block;
        background: #e8f4dc;
        color: #2d5016;
        border: 1px solid #cfe5bf;
        border-radius: 999px;
        padding: 0.2rem 0.65rem;
        font-size: 0.78rem;
        font-weight: 850;
        margin-bottom: 0.8rem;
    }
    .ai-analysis-body {
        color: #1f2933;
        line-height: 1.48;
        font-size: 0.95rem;
    }
    .ai-analysis-body h4 {
        color: #203047;
        font-size: 0.98rem;
        font-weight: 850;
        margin: 0.85rem 0 0.35rem 0;
        padding-top: 0.35rem;
        border-top: 1px solid #e7edf3;
    }
    .ai-analysis-body h4:first-child {
        border-top: none;
        margin-top: 0;
        padding-top: 0;
    }
    .ai-analysis-body p {
        margin: 0.35rem 0 0.65rem 0;
    }
    .ai-analysis-body ul {
        margin: 0.35rem 0 0.75rem 1.05rem;
        padding: 0;
    }
    .ai-analysis-body li {
        margin-bottom: 0.35rem;
    }
    .ranking-table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        overflow: hidden;
        border-radius: 12px;
        font-size: 0.86rem;
    }
    .ranking-table th {
        background: #e8f4dc;
        color: #203047;
        padding: 0.68rem 0.72rem;
        text-align: left;
        font-weight: 850;
        border-bottom: 1px solid #d6e9c8;
    }
    .ranking-table td {
        padding: 0.64rem 0.72rem;
        border-bottom: 1px solid #edf1f5;
        color: #1f2933;
        vertical-align: top;
    }
    .ranking-table tr:nth-child(even) td {
        background: #f8fafc;
    }
    .ranking-money,
    .ranking-pct {
        text-align: right !important;
        white-space: nowrap;
        font-weight: 800;
    }
    .ranking-account {
        max-width: 280px;
        line-height: 1.25;
    }
</style>
"""


def apply_kappo_theme() -> None:
    st.markdown(KAPPO_CSS, unsafe_allow_html=True)


def render_header(title: str, subtitle: str, status: str | None = None) -> None:
    status_html = ""
    if status:
        status_html = f'<span class="status-pill">{html.escape(status)}</span>'
    st.markdown(
        f"""
        <div class="kappo-banner">
            <h1>{html.escape(title)}</h1>
            <p>{html.escape(subtitle)} {status_html}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(title: str) -> None:
    st.markdown(f'<div class="section-title">{html.escape(title)}</div>', unsafe_allow_html=True)
