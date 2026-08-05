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
AND f.ACCOUNTING_YEAR >= 2025
"""


MAPPING_TABLE = """
dev_datalake.bronze.web_app_product_category_mapping
"""


HIERARCHY_TABLE = """
dev_datalake.bronze.sharepoint_map_product_hierarchy
"""


PRODUCT_TABLE = """
dev_datalake.silver.d_sales_product_augmented
"""


SALES_TABLE = """
dev_datalake.gold.f_sales_ledger_combined_full
"""


# ============================================================
# Database helpers
# ============================================================

def execute_sql(sql):
    """
    Execute INSERT / UPDATE statements.
    """
    run_write(sql)



def safe_sql(value):
    """
    Escape values for SQL statements.
    """

    if value is None:
        return "NULL"

    return "'" + str(value).replace("'", "''") + "'"



# ============================================================
# Load product hierarchy
# ============================================================

@st.cache_data(ttl=3600)
def load_hierarchy():

    df = run_query(f"""

        SELECT DISTINCT

            PRODUCT_CATEGORY_UID,

            L0_PRODUCT_FAMILY,
            L1_PRODUCT_SEGMENT,
            L2_COMPONENT_FAMILY,
            L3_MAIN_COMPONENT,
            L5_BONDING_SYSTEM,
            M1_TYPE,
            M2_INSTALLATION_METHOD


        FROM {HIERARCHY_TABLE}


        WHERE

            L0_PRODUCT_FAMILY IS NOT NULL


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



        FROM {PRODUCT_TABLE} p



        INNER JOIN {SALES_TABLE} f

        ON p.PRODUCT_UID = f.PRODUCT_UID



        LEFT JOIN {MAPPING_TABLE} m

        ON p.PRODUCT_UID = m.PRODUCT_UID



        WHERE

            {SALES_FILTER}


    """)


    return df



# ============================================================
# Load products requiring category assignment
# ============================================================

@st.cache_data(ttl=300)
def load_unmapped_products():


    df = run_query(f"""

        SELECT


            p.PRODUCT_UID,

            p.PRODUCT_ID,

            p.PRODUCT_DESC,

            p.PRODUCT_GROUP_ID,

            p.SOURCE,


            SUM(
                f.sales_amount_group
            ) AS SALES_AMOUNT,


            MIN(
                f.ACCOUNTING_YEAR
            ) AS FIRST_SALES_YEAR,


            MAX(
                f.ACCOUNTING_YEAR
            ) AS LAST_SALES_YEAR



        FROM {PRODUCT_TABLE} p



        INNER JOIN {SALES_TABLE} f

        ON p.PRODUCT_UID = f.PRODUCT_UID



        LEFT JOIN {MAPPING_TABLE} m

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



        ORDER BY

            SALES_AMOUNT DESC



    """)


    return df

# ============================================================
# Hierarchy dropdown helpers
# ============================================================

def get_filtered_options(df, selected, column):
    """
    Returns available hierarchy values based on previous selections.
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


    st.subheader(
        "Select Product Category"
    )


    selected = {}


    col1, col2 = st.columns(2)



    with col1:


        selected["L0_PRODUCT_FAMILY"] = st.selectbox(

            "L0 Product Family",

            [
                None
            ]
            +
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
            ]
            +
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
            ]
            +
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
            ]
            +
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
            ]
            +
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
            ]
            +
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
            ]
            +
            get_filtered_options(

                df,

                selected,

                "M2_INSTALLATION_METHOD"

            ),

            key=f"{key_prefix}_m2"

        )



    return selected



# ============================================================
# Find category UID
# ============================================================

def get_category_uid(selection):


    df = run_query(f"""

        SELECT

            PRODUCT_CATEGORY_UID


        FROM {HIERARCHY_TABLE}


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
# Save product category assignment
# ============================================================

def save_mapping(product, category_uid):


    sql = f"""

    INSERT INTO {MAPPING_TABLE}


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
# DATA QUALITY OVERVIEW
# ============================================================

def render_data_quality():


    st.header(
        "📊 Product Category Coverage"
    )


    st.info(
        """
        Monitoring category assignment completeness
        for products with sales activity from 2025 onwards.
        
        Unmapped products are moved to the mapping queue
        for manual category assignment.
        """
    )



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



        FROM {PRODUCT_TABLE} p



        INNER JOIN {SALES_TABLE} f

        ON p.PRODUCT_UID = f.PRODUCT_UID



        LEFT JOIN {MAPPING_TABLE} m

        ON p.PRODUCT_UID = m.PRODUCT_UID



        WHERE

            {SALES_FILTER}



    """)



    total_products = int(
        kpi.iloc[0]["TOTAL_PRODUCTS"]
    )


    mapped_products = int(
        kpi.iloc[0]["MAPPED_PRODUCTS"]
    )


    unmapped_products = int(
        kpi.iloc[0]["UNMAPPED_PRODUCTS"]
    )


    mapping_rate = round(

        mapped_products
        /
        total_products
        *
        100,

        1

    ) if total_products else 0



    c1, c2, c3 = st.columns(3)



    with c1:

        st.plotly_chart(

            gauge_chart(
                "Category Mapping",
                mapping_rate
            ),

            use_container_width=True,

            key="category_mapping_gauge"

        )



    with c2:

        metric_card(

            "Mapped Products",

            f"{mapped_products:,}",

            f"{mapping_rate}% complete",

            "good"

        )



    with c3:

        metric_card(

            "Products Requiring Action",

            f"{unmapped_products:,}",

            "Missing category assignment",

            "bad" if unmapped_products else "good"

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

                *

                100,

                1

            ) AS MAPPING_RATE



        FROM {PRODUCT_TABLE} p



        INNER JOIN {SALES_TABLE} f

        ON p.PRODUCT_UID=f.PRODUCT_UID



        LEFT JOIN {MAPPING_TABLE} m

        ON p.PRODUCT_UID=m.PRODUCT_UID



        WHERE

            {SALES_FILTER}



        GROUP BY

            p.SOURCE



        ORDER BY

            MAPPING_RATE


    """)



    fig = px.bar(

        source_df,

        x="SOURCE",

        y="MAPPING_RATE",

        text="MAPPING_RATE",

        title="Category Mapping % by Source"

    )


    st.plotly_chart(

        fig,

        use_container_width=True

    )

# ============================================================
# SALES COVERAGE VIEW
# ============================================================

def render_sales_coverage():


    st.subheader(
        "💰 Sales Coverage Impact"
    )


    sales_df = run_query(f"""

        SELECT


            CASE

                WHEN m.PRODUCT_UID IS NULL

                THEN 'Unmapped'


                ELSE 'Mapped'


            END AS STATUS,


            SUM(
                f.sales_amount_group
            ) AS SALES_AMOUNT



        FROM {SALES_TABLE} f



        LEFT JOIN {MAPPING_TABLE} m

        ON f.PRODUCT_UID = m.PRODUCT_UID



        WHERE

            {SALES_FILTER}



        GROUP BY

            1


    """)



    fig = px.pie(

        sales_df,

        names="STATUS",

        values="SALES_AMOUNT",

        title="Sales Amount Coverage"

    )


    st.plotly_chart(

        fig,

        use_container_width=True

    )



# ============================================================
# PRODUCT CATEGORY ASSIGNMENT
# ============================================================

def render_mapping():


    st.header(
        "🗂️ Product Category Assignment"
    )


    st.info(
        """
        Products with sales activity from 2025 onwards
        that currently have no category assignment.
        
        Select a product and assign the correct
        product hierarchy classification.
        """
    )



    df_products = load_unmapped_products()



    if df_products.empty:


        st.success(
            "🎉 All products with sales from 2025 onwards are mapped."
        )

        return



    # --------------------------------------------------------
    # Queue KPIs
    # --------------------------------------------------------

    c1, c2 = st.columns(2)



    with c1:

        st.metric(

            "Products requiring mapping",

            f"{len(df_products):,}"

        )



    with c2:

        st.metric(

            "Sales impacted",

            f"{df_products.SALES_AMOUNT.sum():,.0f}"

        )



    st.divider()



    # --------------------------------------------------------
    # Product selection
    # --------------------------------------------------------

    product_uid = st.selectbox(

        "Select product",

        df_products.PRODUCT_UID,


        format_func=lambda x:

        df_products[
            df_products.PRODUCT_UID == x
        ]
        .iloc[0]
        .PRODUCT_ID

    )



    product = df_products[

        df_products.PRODUCT_UID == product_uid

    ].iloc[0]



    st.subheader(
        "Product Details"
    )


    st.write(

        f"""

        **Product ID:** {product.PRODUCT_ID}


        **Description:** {product.PRODUCT_DESC}


        **Source:** {product.SOURCE}


        **Sales Amount:** {product.SALES_AMOUNT:,.0f}

        """

    )



    st.divider()



    # --------------------------------------------------------
    # Category selection
    # --------------------------------------------------------

    hierarchy = load_hierarchy()



    selection = render_hierarchy_selector(

        hierarchy,

        "mapping"

    )



    if st.button(

        "💾 Assign Product Category"

    ):


        category_uid = get_category_uid(

            selection

        )



        if category_uid is None:


            st.error(

                "Please select a complete category hierarchy."

            )



        else:


            save_mapping(

                product,

                category_uid

            )


            st.success(

                "Product category assigned successfully."

            )


            st.cache_data.clear()


            st.rerun()



# ============================================================
# SEARCH PRODUCT
# ============================================================

def render_search():


    st.header(
        "🔍 Search Product"
    )



    df = load_products()



    search = st.text_input(

        "Search by product ID or description"

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

            "📊 Overview",

            "🗂️ Mapping Queue",

            "🔍 Search"

        ]

    )



    with tab1:


        render_data_quality()


        st.divider()


        render_sales_coverage()



    with tab2:


        render_mapping()



    with tab3:


        render_search()