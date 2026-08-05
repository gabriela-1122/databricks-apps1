"""
app.py - Data Quality App
Databricks Streamlit App — ALL files are flat in the same directory.
Started via: streamlit run app.py (defined in app.yaml)
"""
import streamlit as st


import os
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
    "👥Customer Groups AI Suggestion",
    "📦 Products — Category Mapping",
    "📅 Customer Group Management"

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
    print("Hello")
    import overview as _mod
elif page == "👥Customer Groups AI Suggestion":
    try:
        import cust_customer_group as _mod
    except Exception as e:
        st.error(f"Customer Group page failed: {e}")
        st.exception(e)
        _mod = None
elif page == "📦 Products — Category Mapping":
    import prod_category_mapping as _mod
elif page == "📅 Customer Group Management":
    import change_tracking as _mod
else:
    _mod = None

if _mod is not None:
    _mod.render()