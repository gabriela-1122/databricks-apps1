"""
app.py - Data Quality App
Databricks Streamlit App — ALL files are flat in the same directory.
Started via: streamlit run app.py (defined in app.yaml)
"""
import streamlit as st

st.set_page_config(
    page_title="Data Quality App",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui import inject_css
inject_css()


# Pages visible to each role
_DQ_PAGES = [
    "🏠 Overview",
    "👥 Customers — Market Segment",
    "👥 Customers — Customer Groups",
    "👥 Customers — Customer Type",
    "📦 Products — Category Mapping",
    "📅 Change Tracking"

]

with st.sidebar:
    st.markdown("## 🔍 Data Quality App")
    st.markdown("---")

    page = st.radio(
        "Navigation",
        _DQ_PAGES,
        label_visibility="collapsed",
    )

# ── Page routing ──────────────────────────────────────────────────────────────
if page == "🏠 Overview":
    import overview as _mod
elif page == "👥 Customers — Market Segment":
    import cust_market_segment as _mod
elif page == "👥 Customers — Customer Groups":
    import cust_customer_group as _mod
elif page == "👥 Customers — Customer Type":
    import cust_customer_type as _mod
elif page == "📦 Products — Category Mapping":
    import prod_category_mapping as _mod
elif page == "📅 Change Tracking":
    import change_tracking as _mod
else:
    _mod = None

if _mod is not None:
    _mod.render()