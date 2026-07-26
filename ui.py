"""
ui.py - Reusable Streamlit UI components (flat, no subfolders)
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def inject_css():
    st.markdown("""
    <style>
      .metric-card {
        background: white; border-radius: 10px; padding: 18px 22px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        border-left: 5px solid #1F3B73; margin-bottom: 12px;
      }
      .metric-card.good  { border-left-color: #2ECC71; }
      .metric-card.warn  { border-left-color: #F39C12; }
      .metric-card.bad   { border-left-color: #E74C3C; }
      .metric-title { font-size:0.82rem; color:#7F8C8D; font-weight:600;
                      text-transform:uppercase; letter-spacing:0.5px; }
      .metric-value { font-size:2rem; font-weight:700; color:#1F3B73; line-height:1.2; }
      .metric-value-sm { font-size:1.15rem; font-weight:700; color:#1F3B73; line-height:1.3; }
      .metric-value-xs { font-size:0.88rem; font-weight:700; color:#1F3B73; line-height:1.4; }
      .metric-sub   { font-size:0.78rem; color:#95A5A6; margin-top:2px; }
      .section-header { font-size:1.1rem; font-weight:700; color:#1F3B73;
                        border-bottom:2px solid #E8ECF0; padding-bottom:6px; margin:16px 0 12px; }
      .info-box { background:#EBF5FB; border-left:4px solid #2E86C1; border-radius:6px;
                  padding:10px 14px; font-size:0.85rem; color:#1A5276; margin:8px 0; }
    </style>
    """, unsafe_allow_html=True)


def metric_card(title, value, sub="", status="neutral"):
    st.markdown(f"""
    <div class="metric-card {status}">
      <div class="metric-title">{title}</div>
      <div class="metric-value">{value}</div>
      <div class="metric-sub">{sub}</div>
    </div>
    """, unsafe_allow_html=True)


def metric_card_sm(title, value, sub="", status="neutral"):
    """Compact metric card with smaller value font — for long € strings."""
    st.markdown(f"""
    <div class="metric-card {status}">
      <div class="metric-title">{title}</div>
      <div class="metric-value-sm">{value}</div>
      <div class="metric-sub">{sub}</div>
    </div>
    """, unsafe_allow_html=True)


def metric_card_xs(title, value, sub="", status="neutral"):
    """Extra-compact metric card for very long € amounts (e.g. 9-digit totals)."""
    st.markdown(f"""
    <div class="metric-card {status}">
      <div class="metric-title">{title}</div>
      <div class="metric-value-xs">{value}</div>
      <div class="metric-sub">{sub}</div>
    </div>
    """, unsafe_allow_html=True)


def mapping_rate_status(pct):
    if pct >= 90: return "good"
    if pct >= 70: return "warn"
    return "bad"


def gauge_chart(title, value, max_val=100):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value,
        title={"text": title, "font": {"size": 14}},
        number={"suffix": "%", "font": {"size": 24}},
        gauge={
            "axis": {"range": [0, max_val]},
            "bar": {"color": "#1F3B73"},
            "steps": [
                {"range": [0, 70],       "color": "#FADBD8"},
                {"range": [70, 90],      "color": "#FDEBD0"},
                {"range": [90, max_val], "color": "#D5F5E3"},
            ],
            "threshold": {"line": {"color": "#1F3B73", "width": 3}, "thickness": 0.8, "value": 90},
        },
    ))
    fig.update_layout(height=220, margin=dict(l=20, r=20, t=40, b=20))
    return fig


def trend_chart(df, x, y, color=None, title=""):
    fig = px.line(df, x=x, y=y, color=color, title=title,
                  color_discrete_sequence=px.colors.qualitative.Set2)
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=40, b=10),
                      plot_bgcolor="white", paper_bgcolor="white",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="#ECF0F1")
    return fig


def bar_chart(df, x, y, title="", color=None):
    fig = px.bar(df, x=x, y=y, color=color, title=title,
                 color_discrete_sequence=["#1F3B73"], text_auto=True)
    fig.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10),
                      plot_bgcolor="white", paper_bgcolor="white")
    return fig


def info_box(text):
    st.markdown(f'<div class="info-box">ℹ️ {text}</div>', unsafe_allow_html=True)


def section_header(text):
    st.markdown(f'<div class="section-header">{text}</div>', unsafe_allow_html=True)


def changes_dataframe(df, change_col="CHANGE_TYPE"):
    def badge(val):
        if val == "NEW":     return "background-color:#D5F5E3; color:#1E8449"
        if val == "CHANGED": return "background-color:#FDEBD0; color:#B7770D"
        if val == "REMOVED": return "background-color:#FADBD8; color:#922B21"
        return ""
    if change_col in df.columns:
        st.dataframe(df.style.applymap(badge, subset=[change_col]), use_container_width=True)
    else:
        st.dataframe(df, use_container_width=True)