"""cust_customer_group.py - Customer Groups DQ + AI suggestions"""
import json
import streamlit as st
import pandas as pd
import plotly.express as px
from db import run_query
from customer_exceptions import ms_exclusion_clause
from ui import gauge_chart, section_header, info_box, metric_card, mapping_rate_status

ANTHROPIC_API_KEY = dbutils.secrets.get(
    scope="dq-app-secrets",
    key="ANTHROPIC_API_KEY"
)

# Base filter for fact table queries
FSL_CUSTOMER_BASE = """
    VERSION_ID = 'AC'
    AND LEDGER_SOURCE = 'ACTUAL'
    AND ACCOUNTING_YEAR >= 2023
    AND COALESCE(fsl.INTERCO,'') <> 'Interco only'
    AND ENTITY_ID IS NOT NULL
    AND CUSTOMER_BILL_TO_UID IS NOT NULL
"""

IN_SCOPE = """
    AND EXISTS (
        SELECT 1 FROM dev_datalake.gold.f_sales_ledger_combined_full fsl
        WHERE fsl.CUSTOMER_BILL_TO_UID = sc.CUSTOMER_UID
          AND fsl.VERSION_ID = 'AC'
          AND fsl.LEDGER_SOURCE = 'ACTUAL'
          AND fsl.ACCOUNTING_YEAR >= 2023
          AND COALESCE(fsl.INTERCO, '') <> 'Interco only'
          AND fsl.ENTITY_ID IS NOT NULL
          AND fsl.CUSTOMER_BILL_TO_UID IS NOT NULL
    )
"""




@st.cache_data(ttl=3600)
def load_all_groups():
    df = run_query(f"""
        SELECT DISTINCT sc.CUSTOMER_GROUP_DESC
        FROM dev_datalake.silver.d_sales_customer sc
        WHERE sc.TABLE_SOURCE NOT IN ('BUDGET','HISTORICAL')
          AND sc.INTERCO <> 'Interco Only'
          AND sc.CUSTOMER_GROUP_DESC IS NOT NULL
          AND TRIM(sc.CUSTOMER_GROUP_DESC) <> ''
          {IN_SCOPE}
        ORDER BY 1""")
    return df["CUSTOMER_GROUP_DESC"].tolist()


@st.cache_data(ttl=3600, show_spinner=False)
def load_groups_with_sources():
    df = run_query(f"""
    SELECT 
        sc.CUSTOMER_GROUP_DESC,
        concat_ws(',', collect_set(sc.SOURCE)) AS sources
    FROM dev_datalake.silver.d_sales_customer sc
    WHERE sc.TABLE_SOURCE NOT IN ('BUDGET','HISTORICAL')
      AND sc.INTERCO <> 'Interco Only'
      AND sc.CUSTOMER_GROUP_DESC IS NOT NULL
      AND TRIM(sc.CUSTOMER_GROUP_DESC) <> ''
      {IN_SCOPE}
    GROUP BY sc.CUSTOMER_GROUP_DESC
    ORDER BY 1
    """)
    
    col = "SOURCES" if "SOURCES" in df.columns else "sources"
    return dict(zip(df["CUSTOMER_GROUP_DESC"], df[col]))


def find_lookalikes_cached(threshold=0.85):
    from difflib import SequenceMatcher
    try:
        grp_sources = load_groups_with_sources()
    except Exception:
        grp_sources = {g: "" for g in load_all_groups()}
    groups = list(grp_sources.keys())
    groups_lower = [g.lower().strip() for g in groups]
    pairs = []
    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            li, lj = len(groups_lower[i]), len(groups_lower[j])
            if max(li, lj) == 0 or min(li, lj) / max(li, lj) < threshold:
                continue
            score = SequenceMatcher(None, groups_lower[i], groups_lower[j]).ratio()
            if score >= threshold:
                suggestion = groups[i] if li <= lj else groups[j]
                pairs.append({
                    "Group A":             groups[i],
                    "Group B":             groups[j],
                    "Similarity":          f"{score:.0%}",
                    "Suggested Merged Name": suggestion,
                })
    return pairs


def _call_claude(prompt: str, max_tokens: int = 300) -> str:
    """Raw Claude API call with exponential backoff on 429."""
    import urllib.request, urllib.error, time
    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages", data=payload,
                headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_API_KEY,
                         "anthropic-version": "2023-06-01"}, method="POST")
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            text = data["content"][0]["text"].strip()
            if text.startswith("```"):
                text = "\n".join(text.split("\n")[1:-1])
            return text
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 4:
                wait = 2 ** (attempt + 2)  # 4, 8, 16, 32, 64s
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Claude API failed after 5 attempts")


BATCH_SIZE = 25   # 25 customers, names truncated to 60 chars → fits in 4096 output tokens
SLEEP_BETWEEN = 2  # seconds between batches to stay under rate limits


def ai_suggest_group(customer_name: str, existing_groups: list) -> dict:
    """Single-customer suggestion — returns dict with recommended_group, is_existing,
    justification, confidence (0-100)."""
    groups_list = "\n".join(f"- {g}" for g in sorted(set(existing_groups))[:100])
    prompt = f"""You are a B2B data steward. A customer named "{customer_name}" has no customer group assigned.
1. Check if an existing group clearly applies (e.g. "ArcelorMittal Dunkerque" → "ARCELORMITTAL GROUP").
2. If yes, recommend it. If not, suggest a new group name (UPPERCASE, max 5 words).
3. Only recommend existing groups — do NOT propose new ones if an existing match exists.
4. Rate your confidence 0-100. Only return high confidence (>=90) if you are very sure.

Existing groups:
{groups_list}

Respond ONLY in JSON (no markdown):
{{"recommended_group": "<n>", "is_existing": true/false, "justification": "<max 2 sentences>", "confidence": <0-100>}}"""
    return json.loads(_call_claude(prompt, max_tokens=300))


def _parse_batch_response(text: str, customers: list) -> list:
    """Parse Claude JSON response, recovering partial results if the output was truncated."""
    import re
    # Try clean parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Salvage: extract all complete {...} objects from the array before truncation
    objects = []
    for m in re.finditer(r'[{][^{}]+[}]', text, re.DOTALL):
        try:
            obj = json.loads(m.group())
            # Only keep objects that have the expected keys
            if "recommended_group" in obj and "confidence" in obj:
                objects.append(obj)
        except json.JSONDecodeError:
            continue
    if objects:
        return objects
    # Nothing salvageable — return empty stubs so the batch doesn't crash the whole run
    return [{"index": i+1, "recommended_group": "", "is_existing": False,
             "justification": "parse error", "confidence": 0}
            for i in range(len(customers))]



def ai_suggest_batch(customers: list, existing_groups: list) -> list:
    """One API call for a batch of customers (up to BATCH_SIZE).
    customers: list of dicts with keys customer_uid, customer_desc, source.
    Returns list of result dicts enriched with customer_uid/desc/source."""
    # Truncate inputs to 60 chars so the response always fits within max_tokens=4096
    groups_list   = "\n".join(f"- {g[:60]}" for g in sorted(set(existing_groups)))
    customers_txt = "\n".join(
        f"{i+1}. {c['customer_desc'][:60]}" for i, c in enumerate(customers)
    )
    prompt = f"""You are a B2B data steward classifying unassigned customers into groups.

Rules:
- For each customer, check if an EXISTING group clearly applies. Prefer existing groups over new ones.
- Only suggest a new group name (UPPERCASE, max 5 words) if truly no existing group fits.
- Be conservative with confidence: score >=90 only when you are genuinely certain.
- Keep justification to 5 words maximum.

Existing groups:
{groups_list}

Customers to classify:
{customers_txt}

Respond ONLY with a JSON array (no markdown, no preamble), one object per customer in order:
[
  {{"index": 1, "recommended_group": "<n>", "is_existing": true/false, "justification": "<5 words>", "confidence": <0-100>}},
  ...
]"""
    results = _parse_batch_response(_call_claude(prompt, max_tokens=4096), customers)
    for r in results:
        idx = r.get("index", 1) - 1
        if 0 <= idx < len(customers):
            r["customer_uid"]  = customers[idx]["customer_uid"]
            r["customer_desc"] = customers[idx]["customer_desc"]
            r["source"]        = customers[idx].get("source", "")
    return results



YEAR_OPTIONS = ["All years", 2023, 2024, 2025, 2026]

def render():
    st.title("👥 Customers — Customer Groups")
    info_box(
        "Scope: customers with at least one transaction in f_sales_ledger_combined since 2023, "
        "excluding BUDGET source and Interco customers (fsl.INTERCO ≠ 'Interco only' / sc.INTERCO ≠ 1). "
        "Mapping rate = % of in-scope customers with a CUSTOMER_GROUP_DESC."
    )

    col1, _ = st.columns([2, 4])
    with col1:
        try:
            src_df = run_query(f"""
                SELECT DISTINCT sc.SOURCE
                FROM dev_datalake.silver.d_sales_customer sc
                WHERE sc.TABLE_SOURCE NOT IN ('BUDGET','HISTORICAL')
                  AND sc.INTERCO <> 'Interco Only'
                  {IN_SCOPE}
                ORDER BY 1""")
            sel_src = st.multiselect("Filter by Source", src_df["SOURCE"].tolist(),
                                     placeholder="All sources", key="cg_src")
        except Exception:
            sel_src = []

    src_clause     = ("AND sc.SOURCE IN (" + ",".join(f"'{s}'" for s in sel_src) + ")") if sel_src else ""
    sel_yr = st.selectbox("Year", YEAR_OPTIONS, key="cg_yr")
    yr_clause_fsl  = f"AND fsl.ACCOUNTING_YEAR = {sel_yr}" if sel_yr != "All years" else ""

    src_clause_chg = ("AND SOURCE IN ("    + ",".join(f"'{s}'" for s in sel_src) + ")") if sel_src else ""
    # ── Plain-English filter summary ──────────────────────────────────────────
    _active_filters = ["Source: **" + (", ".join(sel_src) if sel_src else "All") + "**", "Year: **" + (str(sel_yr) if sel_yr != "All years" else "All years") + "**", "Customer group: excluding customers without transactions (in-scope only)"]
    info_box(
        "Customers with transactions since 2023, excluding BUDGET and Interco.<br>"
        "Active filters: " + " &nbsp;·&nbsp; ".join(_active_filters)
    )

    st.markdown("---")

    # ── KPI ───────────────────────────────────────────────────────────────────
    section_header("📊 Mapping Rate")
    try:
        kpi = run_query(f"""
            SELECT
                SUM(ABS(fsl.SALES_AMOUNT_GROUP))                                   AS total_amt,
                SUM(CASE WHEN sc.CUSTOMER_GROUP_DESC IS NOT NULL
                         AND TRIM(sc.CUSTOMER_GROUP_DESC) <> ''
                         THEN ABS(fsl.SALES_AMOUNT_GROUP) ELSE 0 END)              AS mapped_amt,
                COUNT(DISTINCT fsl.CUSTOMER_BILL_TO_ID)                       AS total_cust,
                COUNT(DISTINCT CASE WHEN sc.CUSTOMER_GROUP_DESC IS NOT NULL
                         AND TRIM(sc.CUSTOMER_GROUP_DESC) <> ''
                         THEN fsl.CUSTOMER_BILL_TO_ID END)                    AS mapped_cust
            FROM dev_datalake.gold.f_sales_ledger_combined_full fsl
            LEFT JOIN dev_datalake.silver.d_sales_customer sc
              ON fsl.CUSTOMER_BILL_TO_UID = sc.CUSTOMER_UID
            WHERE {FSL_CUSTOMER_BASE}
              {src_clause} {yr_clause_fsl}""")
        kpi.columns = [c.upper() for c in kpi.columns]
        total_amt  = float(kpi["TOTAL_AMT"].iloc[0]  or 0)
        mapped_amt = float(kpi["MAPPED_AMT"].iloc[0] or 0)
        total_cust  = int(kpi["TOTAL_CUST"].iloc[0]  or 0)
        mapped_cust = int(kpi["MAPPED_CUST"].iloc[0] or 0)
        pct = round(mapped_amt / total_amt * 100, 1) if total_amt else 0
        c1, c2, c3 = st.columns(3)
        with c1: st.plotly_chart(gauge_chart("Mapping Rate (€)", pct), use_container_width=True, key="cg_g")
        with c2:
            metric_card("Total Sales €",   f"€ {total_amt:,.0f}",  "", "neutral")
            metric_card("Mapped €",        f"€ {mapped_amt:,.0f}", f"{pct}%", mapping_rate_status(pct))
        with c3:
            metric_card("Unallocated €",   f"€ {total_amt-mapped_amt:,.0f}", "", "bad" if total_amt > mapped_amt else "good")
            metric_card("Customers total", f"{total_cust:,}", f"{mapped_cust:,} mapped", "neutral")
    except Exception as e:
        st.error(str(e))

    section_header("📈 Mapping Rate by Source")
    extra_src     = src_clause
    extra_src_chg = src_clause_chg
    try:
        by_src = run_query(f"""
            SELECT sc.SOURCE,
                COUNT(*) AS total,
                COUNT(CASE WHEN sc.CUSTOMER_GROUP_DESC IS NOT NULL
                           AND TRIM(sc.CUSTOMER_GROUP_DESC) <> '' THEN 1 END) AS mapped,
                ROUND(COUNT(CASE WHEN sc.CUSTOMER_GROUP_DESC IS NOT NULL
                           AND TRIM(sc.CUSTOMER_GROUP_DESC) <> '' THEN 1 END)
                    / NULLIF(COUNT(*), 0) * 100, 1) AS pct
            FROM dev_datalake.silver.d_sales_customer sc
            WHERE sc.TABLE_SOURCE NOT IN ('BUDGET','HISTORICAL')
              AND sc.INTERCO <> 'Interco Only'
              {IN_SCOPE}
              {src_clause}
            GROUP BY 1 ORDER BY 4 ASC""")
        fig = px.bar(by_src, x="SOURCE", y="PCT", color="PCT",
                     color_continuous_scale=["#d62728", "#ff7f0e", "#2ca02c"],
                     range_color=[0, 100], text="PCT",
                     labels={"SOURCE": "Source", "PCT": "Mapped %"},
                     title="Customer Group Mapping % by Source (in-scope customers, txn ≥ 2023)")
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(coloraxis_showscale=False, height=350)
        clicked = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="cg_bar")
        clicked_src = None
        if clicked and clicked.get("selection", {}).get("points"):
            clicked_src = clicked["selection"]["points"][0].get("x")
            st.info(f"🔍 Filtered to source: **{clicked_src}**")
        extra_src     = f"AND sc.SOURCE = '{clicked_src}'" if clicked_src else src_clause
        extra_src_chg = f"AND SOURCE = '{clicked_src}'" if clicked_src else src_clause_chg
    except Exception as e:
        st.error(str(e))

    # ── Unassigned customers ──────────────────────────────────────────────────
    section_header("❌ Unassigned Customers (in scope)")
    try:
        un = run_query(f"""
            SELECT sc.SOURCE, sc.CUSTOMER_UID, sc.CUSTOMER_ID, sc.CUSTOMER_DESC,
                   sc.CUSTOMER_TYPE, sc.COUNTRY_UID
            FROM dev_datalake.silver.d_sales_customer sc
            WHERE sc.TABLE_SOURCE NOT IN ('BUDGET','HISTORICAL')
              AND sc.INTERCO <> 'Interco Only'
              AND (sc.CUSTOMER_GROUP_DESC IS NULL OR TRIM(sc.CUSTOMER_GROUP_DESC) = '')
              {IN_SCOPE}
              {extra_src}
              {ms_exclusion_clause("sc.CUSTOMER_ID")}
            ORDER BY sc.SOURCE, sc.CUSTOMER_DESC
            LIMIT 500""")
        st.caption(f"{len(un)} unassigned in-scope customers (max 500)")
        st.dataframe(un, use_container_width=True)
    except Exception as e:
        st.error(str(e))

    # ── Look-alike detection ──────────────────────────────────────────────────
    section_header("🔍 Look-Alike Group Detection")
    info_box("Groups with ≥85% name similarity among in-scope customers. Results cached for the session.")
    if st.button("Run Look-Alike Analysis", key="cg_lookalike_btn"):
        with st.spinner("Analysing group names…"):
            pairs = find_lookalikes_cached()
        if pairs:
            df_pairs = pd.DataFrame(pairs)
            st.warning(f"⚠️ {len(pairs)} potential duplicate group pairs found.")
            st.dataframe(df_pairs, use_container_width=True)
            st.download_button("⬇️ Download CSV", df_pairs.to_csv(index=False),
                               "lookalike_groups.csv", "text/csv")
        else:
            st.success("✅ No look-alike duplicates found at 85% threshold.")

    # ── AI single-customer suggestion ─────────────────────────────────────────
    section_header("🤖 AI Customer Group Suggestion (Single)")
    if not ANTHROPIC_API_KEY:
        st.error("ANTHROPIC_API_KEY environment variable not set.")
        return
    try:
        un2 = run_query(f"""
            SELECT sc.CUSTOMER_UID, sc.CUSTOMER_ID, sc.CUSTOMER_DESC, sc.SOURCE
            FROM dev_datalake.silver.d_sales_customer sc
            WHERE sc.TABLE_SOURCE NOT IN ('BUDGET','HISTORICAL')
              AND sc.INTERCO <> 'Interco Only'
              AND (sc.CUSTOMER_GROUP_DESC IS NULL OR TRIM(sc.CUSTOMER_GROUP_DESC) = '')
              {IN_SCOPE}
              {extra_src}
              {ms_exclusion_clause("sc.CUSTOMER_ID")}
            ORDER BY sc.SOURCE, sc.CUSTOMER_DESC
            LIMIT 500""")
        if len(un2) == 0:
            st.success("✅ No unallocated customers.")
        else:
            # Show full info in selectbox label: source + ID + name
            un2["_label"] = un2.apply(
                lambda r: f"[{r['SOURCE']}] {r['CUSTOMER_ID']} — {r['CUSTOMER_DESC']}", axis=1
            ) if "CUSTOMER_ID" in un2.columns else un2["CUSTOMER_DESC"]
            sel_label = st.selectbox("Select unallocated customer:", un2["_label"].tolist(), key="ai_cust_sel")
            sel_row = un2[un2["_label"] == sel_label].iloc[0]
            st.caption(
                f"**Source:** {sel_row.get('SOURCE', '—')}  ·  "
                f"**Customer ID:** {sel_row.get('CUSTOMER_ID', '—')}  ·  "
                f"**Name:** {sel_row.get('CUSTOMER_DESC', '—')}"
            )
            if st.button("🤖 Ask Claude for Group Suggestion", key="ai_btn"):
                existing = load_all_groups()
                with st.spinner(f"Asking Claude about '{sel_row['CUSTOMER_DESC']}'…"):
                    result = ai_suggest_group(sel_row["CUSTOMER_DESC"], existing)
                confidence = result.get("confidence", 0)
                conf_color = "green" if confidence >= 90 else "orange" if confidence >= 70 else "red"
                tag = "✅ Existing group" if result.get("is_existing") else "🆕 New group"
                st.markdown("#### 💡 Claude's Suggestion")
                st.success(f"{tag}: **{result.get('recommended_group')}**")
                st.markdown(
                    f"Confidence: <span style='color:{conf_color};font-weight:bold'>{confidence}%</span>"
                    f" — _{result.get('justification')}_",
                    unsafe_allow_html=True,
                )
    except Exception as e:
        st.error(str(e))

    # ── AI bulk suggestions (≥90% confidence, existing groups only) ───────────
    section_header("🤖 AI Bulk Group Suggestions (≥90% confidence)")
    info_box(
        f"Sends unassigned customers to Claude in batches of {BATCH_SIZE} with automatic retry on rate limits. "
        "Only suggestions matching an <b>existing group</b> with ≥90% confidence are shown. "
        "Results are for reference only — apply changes manually in the source ERP."
    )

    try:
        un_bulk = run_query(f"""
            SELECT sc.CUSTOMER_UID, sc.CUSTOMER_DESC, sc.SOURCE
            FROM dev_datalake.silver.d_sales_customer sc
            WHERE sc.TABLE_SOURCE NOT IN ('BUDGET','HISTORICAL')
              AND sc.INTERCO <> 'Interco Only'
              AND (sc.CUSTOMER_GROUP_DESC IS NULL OR TRIM(sc.CUSTOMER_GROUP_DESC) = '')
              {IN_SCOPE}
              {extra_src}
              {ms_exclusion_clause("sc.CUSTOMER_ID")}
            ORDER BY sc.CUSTOMER_DESC
            LIMIT 1000""")
        total_unassigned = len(un_bulk)
    except Exception as e:
        st.error(str(e))
        un_bulk = pd.DataFrame()
        total_unassigned = 0

    if total_unassigned == 0:
        st.success("✅ No unassigned customers to process.")
    else:
        import math
        n_batches = math.ceil(total_unassigned / BATCH_SIZE)
        st.caption(
            f"{total_unassigned} unassigned customers → {n_batches} batch(es) of {BATCH_SIZE}. "
            f"429 errors are retried automatically with backoff."
        )

        if "bulk_suggestions" not in st.session_state:
            st.session_state["bulk_suggestions"] = None

        col_run, col_clear = st.columns([2, 6])
        with col_run:
            run_bulk = st.button("🚀 Run Bulk AI Analysis", key="cg_bulk_btn")
        with col_clear:
            if st.session_state["bulk_suggestions"] is not None:
                if st.button("🗑️ Clear results", key="cg_bulk_clear"):
                    st.session_state["bulk_suggestions"] = None
                    st.rerun()

        if run_bulk:
            import time
            existing = load_all_groups()
            customers = [
                {"customer_uid": r["CUSTOMER_UID"],
                 "customer_desc": r["CUSTOMER_DESC"],
                 "source": r["SOURCE"]}
                for _, r in un_bulk.iterrows()
            ]
            all_results = []
            errors = []
            progress = st.progress(0, text="Starting…")
            for b in range(n_batches):
                batch = customers[b * BATCH_SIZE : (b + 1) * BATCH_SIZE]
                progress.progress(
                    b / n_batches,
                    text=f"Batch {b+1}/{n_batches} ({len(batch)} customers)…"
                )
                try:
                    results = ai_suggest_batch(batch, existing)
                    all_results.extend(results)
                except Exception as e:
                    errors.append(f"Batch {b+1}: {e}")
                if b < n_batches - 1:
                    time.sleep(SLEEP_BETWEEN)
            progress.progress(1.0, text=f"Done ✅  ({len(all_results)} processed)")
            if errors:
                st.warning("Some batches failed:\n" + "\n".join(errors))
            st.session_state["bulk_suggestions"] = all_results

        if st.session_state["bulk_suggestions"]:
            raw = st.session_state["bulk_suggestions"]
            high_conf = [
                r for r in raw
                if r.get("confidence", 0) >= 90 and r.get("is_existing", False)
            ]
            all_conf = sorted(raw, key=lambda r: -r.get("confidence", 0))

            st.markdown(
                f"**{len(high_conf)} high-confidence suggestions** (existing group, ≥90%) "
                f"out of {len(raw)} total processed."
            )

            tab_high, tab_all = st.tabs([
                f"✅ High confidence ({len(high_conf)})",
                f"📋 All results ({len(raw)})",
            ])

            def make_df(rows):
                return pd.DataFrame([{
                    "Customer":        r.get("customer_desc", ""),
                    "Source":          r.get("source", ""),
                    "Suggested Group": r.get("recommended_group", ""),
                    "Existing?":       "✅ Yes" if r.get("is_existing") else "🆕 New",
                    "Confidence":      r.get("confidence", 0),
                    "Justification":   r.get("justification", ""),
                } for r in rows])

            with tab_high:
                if high_conf:
                    df_high = make_df(high_conf)
                    st.dataframe(
                        df_high.style.background_gradient(
                            subset=["Confidence"], cmap="RdYlGn", vmin=0, vmax=100
                        ),
                        use_container_width=True,
                    )
                    st.download_button(
                        "⬇️ Download high-confidence suggestions (CSV)",
                        df_high.to_csv(index=False),
                        file_name="group_suggestions_high_confidence.csv",
                        mime="text/csv", key="dl_high",
                    )
                else:
                    st.info("No existing-group matches met the ≥90% confidence threshold.")

            with tab_all:
                df_all = make_df(all_conf)
                st.dataframe(
                    df_all.style.background_gradient(
                        subset=["Confidence"], cmap="RdYlGn", vmin=0, vmax=100
                    ),
                    use_container_width=True,
                )
                st.download_button(
                    "⬇️ Download all results (CSV)",
                    df_all.to_csv(index=False),
                    file_name="group_suggestions_all.csv",
                    mime="text/csv", key="dl_all",
                )