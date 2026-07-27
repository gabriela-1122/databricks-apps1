import streamlit as st
import pandas as pd
import plotly.express as px
from ui import (
    inject_css,
    metric_card,
    metric_card_sm,
    metric_card_xs,
    mapping_rate_status,
    gauge_chart,
    bar_chart,
    info_box,
    section_header
)

from db import run_query, run_write


# ============================================================
# Configuration
# ============================================================

SALES_FILTER = """
f.VERSION_ID = 'AC'
AND f.SALES_TYPE_ID IN ('DS','CN')
AND f.ACCOUNTING_YEAR >= 2026
"""


# ============================================================
# Database helpers
# ============================================================

def execute_sql(sql):
    """
    Execute INSERT / UPDATE / DELETE statements.
    """
    run_write(sql)



def safe_sql(value):
    """
    Escape strings for SQL.
    """
    if value is None:
        return "NULL"

    return "'" + str(value).replace("'", "''") + "'"



# ============================================================
# Load category hierarchy
# ============================================================

@st.cache_data(ttl=3600)
def load_hierarchy():

    df = run_query("""
        SELECT DISTINCT

            PRODUCT_CATEGORY_UID,

            L0_PRODUCT_FAMILY,
            L1_PRODUCT_SEGMENT,
            L2_COMPONENT_FAMILY,
            L3_MAIN_COMPONENT,
            L5_BONDING_SYSTEM,
            M1_TYPE,
            M2_INSTALLATION_METHOD


        FROM dev_datalake.bronze.sharepoint_map_product_hierarchy


        WHERE L0_PRODUCT_FAMILY IS NOT NULL

    """)


    return df



# ============================================================
# Load products with mapping status
# ============================================================

@st.cache_data(ttl=300)
def load_products():

    df = run_query(f"""

        SELECT DISTINCT

            p.PRODUCT_UID,
            p.PRODUCT_ID,
            p.PRODUCT_DESC,
            p.PRODUCT_GROUP_ID,
            p.SOURCE,

            m.PRODUCT_CATEGORY_UID


        FROM dev_datalake.silver.d_sales_product_augmented p


        INNER JOIN 
        dev_datalake.gold.f_sales_ledger_combined_full f

        ON p.PRODUCT_UID = f.PRODUCT_UID


        LEFT JOIN
        dev_datalake.bronze.web_app_product_category_mapping m

        ON p.PRODUCT_UID = m.PRODUCT_UID


        WHERE
        {SALES_FILTER}


    """)


    return df



# ============================================================
# Load unmapped products
# ============================================================

@st.cache_data(ttl=300)
def load_unmapped_products():


    df = run_query(f"""

        SELECT DISTINCT

            p.PRODUCT_UID,
            p.PRODUCT_ID,
            p.PRODUCT_DESC,
            p.PRODUCT_GROUP_ID,
            p.SOURCE,

            SUM(f.sales_amount_group) AS SALES_AMOUNT


        FROM dev_datalake.silver.d_sales_product_augmented p


        INNER JOIN 
        dev_datalake.gold.f_sales_ledger_combined_full f

        ON p.PRODUCT_UID = f.PRODUCT_UID


        LEFT JOIN
        dev_datalake.bronze.web_app_product_category_mapping m

        ON p.PRODUCT_UID = m.PRODUCT_UID


        WHERE
        {SALES_FILTER}

        AND m.PRODUCT_UID IS NULL


        GROUP BY

            p.PRODUCT_UID,
            p.PRODUCT_ID,
            p.PRODUCT_DESC,
            p.PRODUCT_GROUP_ID,
            p.SOURCE


        ORDER BY SALES_AMOUNT DESC


    """)


    return df

# ============================================================
# Hierarchy dropdown helpers
# ============================================================

def get_filtered_options(df, selected, column):
    """
    Returns valid options based on previous selections.
    """

    filtered = df.copy()

    for key, value in selected.items():

        if value:
            filtered = filtered[
                filtered[key] == value
            ]


    return sorted(
        filtered[column]
        .dropna()
        .unique()
        .tolist()
    )



def render_hierarchy_selector(df, key_prefix):

    st.subheader("Select Product Category")


    col1, col2 = st.columns(2)


    selected = {}


    with col1:

        selected["L0_PRODUCT_FAMILY"] = st.selectbox(
            "L0 Product Family",
            [
                None
            ] +
            get_filtered_options(
                df,
                {},
                "L0_PRODUCT_FAMILY"
            ),
            key=f"{key_prefix}_l0"
        )


        selected["L1_PRODUCT_SEGMENT"] = st.selectbox(
            "L1 Product Segment",
            [
                None
            ] +
            get_filtered_options(
                df,
                {
                    "L0_PRODUCT_FAMILY":
                    selected["L0_PRODUCT_FAMILY"]
                },
                "L1_PRODUCT_SEGMENT"
            ),
            key=f"{key_prefix}_l1"
        )


        selected["L2_COMPONENT_FAMILY"] = st.selectbox(
            "L2 Component Family",
            [
                None
            ] +
            get_filtered_options(
                df,
                {
                    "L0_PRODUCT_FAMILY":
                    selected["L0_PRODUCT_FAMILY"],

                    "L1_PRODUCT_SEGMENT":
                    selected["L1_PRODUCT_SEGMENT"]
                },
                "L2_COMPONENT_FAMILY"
            ),
            key=f"{key_prefix}_l2"
        )


    with col2:

        selected["L3_MAIN_COMPONENT"] = st.selectbox(
            "L3 Main Component",
            [
                None
            ] +
            get_filtered_options(
                df,
                selected,
                "L3_MAIN_COMPONENT"
            ),
            key=f"{key_prefix}_l3"
        )


        selected["L5_BONDING_SYSTEM"] = st.selectbox(
            "L5 Bonding System",
            [
                None
            ] +
            get_filtered_options(
                df,
                selected,
                "L5_BONDING_SYSTEM"
            ),
            key=f"{key_prefix}_l5"
        )


        selected["M1_TYPE"] = st.selectbox(
            "M1 Type",
            [
                None
            ] +
            get_filtered_options(
                df,
                selected,
                "M1_TYPE"
            ),
            key=f"{key_prefix}_m1"
        )


        selected["M2_INSTALLATION_METHOD"] = st.selectbox(
            "M2 Installation Method",
            [
                None
            ] +
            get_filtered_options(
                df,
                selected,
                "M2_INSTALLATION_METHOD"
            ),
            key=f"{key_prefix}_m2"
        )


    return selected



# ============================================================
# Find Category UID
# ============================================================

def get_category_uid(selection):


    df = run_query(f"""

        SELECT PRODUCT_CATEGORY_UID

        FROM dev_datalake.bronze.sharepoint_map_product_hierarchy


        WHERE

        L0_PRODUCT_FAMILY =
        {safe_sql(selection["L0_PRODUCT_FAMILY"])}

        AND L1_PRODUCT_SEGMENT =
        {safe_sql(selection["L1_PRODUCT_SEGMENT"])}

        AND L2_COMPONENT_FAMILY =
        {safe_sql(selection["L2_COMPONENT_FAMILY"])}

        AND L3_MAIN_COMPONENT =
        {safe_sql(selection["L3_MAIN_COMPONENT"])}

        AND L5_BONDING_SYSTEM =
        {safe_sql(selection["L5_BONDING_SYSTEM"])}

        AND M1_TYPE =
        {safe_sql(selection["M1_TYPE"])}

        AND M2_INSTALLATION_METHOD =
        {safe_sql(selection["M2_INSTALLATION_METHOD"])}


        LIMIT 1

    """)


    if df.empty:
        return None


    return df.iloc[0]["PRODUCT_CATEGORY_UID"]



# ============================================================
# Save Mapping
# ============================================================

def save_mapping(product, category_uid):


    sql = f"""

    INSERT INTO 
    dev_datalake.bronze.web_app_product_category_mapping


    (
        PRODUCT_UID,
        PRODUCT_ID,
        PRODUCT_DESC,
        PRODUCT_CATEGORY_UID,
        LAST_UPDATED
    )


    VALUES


    (
        {safe_sql(product.PRODUCT_UID)},
        {safe_sql(product.PRODUCT_ID)},
        {safe_sql(product.PRODUCT_DESC)},
        {safe_sql(category_uid)},
        CURRENT_TIMESTAMP
    )

    """


    execute_sql(sql)



# ============================================================
# DATA QUALITY TAB
# ============================================================

def render_data_quality():



    # --------------------------------------------------------
    # KPI Cards
    # --------------------------------------------------------

    kpi = run_query(f"""

        SELECT


        COUNT(DISTINCT p.PRODUCT_UID)
            AS TOTAL_PRODUCTS,


        COUNT(DISTINCT m.PRODUCT_UID)
            AS MAPPED_PRODUCTS,


        COUNT(DISTINCT p.PRODUCT_UID)
        -
        COUNT(DISTINCT m.PRODUCT_UID)
            AS UNMAPPED_PRODUCTS



        FROM dev_datalake.silver.d_sales_product_augmented p


        INNER JOIN
        dev_datalake.gold.f_sales_ledger_combined_full f

        ON p.PRODUCT_UID=f.PRODUCT_UID


        LEFT JOIN
        dev_datalake.bronze.web_app_product_category_mapping m

        ON p.PRODUCT_UID=m.PRODUCT_UID


        WHERE
        {SALES_FILTER}

    """)


    total = int(kpi.iloc[0]["TOTAL_PRODUCTS"])
    mapped = int(kpi.iloc[0]["MAPPED_PRODUCTS"])
    unmapped = int(kpi.iloc[0]["UNMAPPED_PRODUCTS"])


    rate = round(
        mapped / total * 100,
        1
    ) if total else 0



    c1,c2,c3,c4 = st.columns(4)


    c1.metric(
        "Total Products",
        f"{total:,}"
    )

    c2.metric(
        "Mapped",
        f"{mapped:,}"
    )


    c3.metric(
        "Unmapped",
        f"{unmapped:,}"
    )


    c4.metric(
        "Mapping Rate",
        f"{rate}%"
    )



    st.divider()



    # --------------------------------------------------------
    # Mapping rate by source
    # --------------------------------------------------------

    st.subheader(
        "📈 Mapping Rate by Source"
    )


    source_df = run_query(f"""

        SELECT


        p.SOURCE,


        COUNT(DISTINCT p.PRODUCT_UID)
            AS TOTAL_PRODUCTS,


        COUNT(DISTINCT m.PRODUCT_UID)
            AS MAPPED_PRODUCTS,


        ROUND(

        COUNT(DISTINCT m.PRODUCT_UID)
        /
        COUNT(DISTINCT p.PRODUCT_UID)
        *100

        ,1)

        AS MAPPING_RATE



        FROM dev_datalake.silver.d_sales_product_augmented p


        INNER JOIN
        dev_datalake.gold.f_sales_ledger_combined_full f

        ON p.PRODUCT_UID=f.PRODUCT_UID


        LEFT JOIN
        dev_datalake.bronze.web_app_product_category_mapping m

        ON p.PRODUCT_UID=m.PRODUCT_UID



        WHERE
        {SALES_FILTER}


        GROUP BY p.SOURCE

        ORDER BY MAPPING_RATE


    """)


    fig = px.bar(
        source_df,
        x="SOURCE",
        y="MAPPING_RATE",
        text="MAPPING_RATE",
        title="Mapping % by Source"
    )


    st.plotly_chart(
        fig,
        use_container_width=True
    )



    st.divider()



    # --------------------------------------------------------
    # Sales impact
    # --------------------------------------------------------

    st.subheader(
        "💰 Sales Amount Coverage"
    )


    sales_df = run_query(f"""

        SELECT


        CASE
        WHEN m.PRODUCT_UID IS NULL
        THEN 'Unmapped'

        ELSE 'Mapped'

        END AS STATUS,


        SUM(f.sales_amount_group)
            AS SALES_AMOUNT



        FROM dev_datalake.gold.f_sales_ledger_combined_full f


        LEFT JOIN
        dev_datalake.bronze.web_app_product_category_mapping m

        ON f.PRODUCT_UID=m.PRODUCT_UID


        WHERE
        {SALES_FILTER}


        GROUP BY 1

    """)



    fig2 = px.pie(
        sales_df,
        names="STATUS",
        values="SALES_AMOUNT",
        title="Mapped vs Unmapped Sales"
    )


    st.plotly_chart(
        fig2,
        use_container_width=True
    )

    # ============================================================
# PRODUCT MAPPING TAB
# ============================================================

def render_mapping():

    st.header("🗂️ Product Mapping")


    df_products = load_unmapped_products()


    if df_products.empty:

        st.success(
            "All products are mapped 🎉"
        )
        return



    product_uid = st.selectbox(
        "Select Product",
        df_products.PRODUCT_UID,
        format_func=lambda x:
        df_products[
            df_products.PRODUCT_UID == x
        ].iloc[0].PRODUCT_ID
    )



    product = df_products[
        df_products.PRODUCT_UID == product_uid
    ].iloc[0]



    st.write(
        f"""
        **Product ID:** {product.PRODUCT_ID}

        **Description:** {product.PRODUCT_DESC}

        **Source:** {product.SOURCE}
        """
    )


    hierarchy = load_hierarchy()


    selection = render_hierarchy_selector(
        hierarchy,
        "mapping"
    )


    if st.button(
        "💾 Save Mapping"
    ):


        category_uid = get_category_uid(
            selection
        )


        if category_uid is None:

            st.error(
                "Invalid hierarchy combination"
            )


        else:

            save_mapping(
                product,
                category_uid
            )


            st.success(
                "Mapping saved"
            )

            st.cache_data.clear()

            st.rerun()



# ============================================================
# SEARCH TAB
# ============================================================

def render_search():


    st.header(
        "🔍 Search Product"
    )


    df = load_products()


    search = st.text_input(
        "Search"
    )


    if search:


        result = df[
            df.PRODUCT_ID.str.contains(
                search,
                case=False,
                na=False
            )
            |
            df.PRODUCT_DESC.str.contains(
                search,
                case=False,
                na=False
            )
        ]


        st.dataframe(
            result,
            use_container_width=True
        )



# ============================================================
# MAIN APP
# ============================================================

def render():

    inject_css()
    st.title(
        "📦 Product Category Mapping"
    )


    tab1, tab2, tab3 = st.tabs(
        [
            "📊 Data Quality",
            "🗂️ Mapping",
            "🔍 Search"
        ]
    )



    with tab1:

        render_data_quality()



    with tab2:

        render_mapping()



    with tab3:

        render_search()