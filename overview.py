import pandas as pd
import plotly.express as px
import streamlit as st

from db import run_query
from ui import section_header, info_box


# -----------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------

ISSUE_TABLE = (
    "dev_datalake.bronze.dq_issue_tracking"
)


SALES_TABLE = (
    "dev_datalake.gold.f_sales_ledger_combined_full"
)


# -----------------------------------------------------------------------
# Load issue KPIs
# -----------------------------------------------------------------------

def load_issue_kpis():

    return run_query(f"""

        SELECT


            COUNT(*) AS TOTAL_ISSUES,


            SUM(

                CASE

                    WHEN STATUS = 'Open'

                    THEN 1

                    ELSE 0

                END

            ) AS OPEN_ISSUES,


            SUM(

                CASE

                    WHEN STATUS = 'Under Investigation'

                    THEN 1

                    ELSE 0

                END

            ) AS INVESTIGATION_ISSUES,


            SUM(

                CASE

                    WHEN STATUS = 'Resolved'

                    THEN 1

                    ELSE 0

                END

            ) AS RESOLVED_ISSUES



        FROM {ISSUE_TABLE}



    """)

# -----------------------------------------------------------------------
# Issues by data domain
# -----------------------------------------------------------------------

def load_domain_summary():

    return run_query(f"""

        SELECT


            CASE


                WHEN ISSUE_TYPE LIKE '%Customer%'

                THEN 'Customer'


                WHEN ISSUE_TYPE LIKE '%Product%'

                THEN 'Product'


                ELSE 'Other'


            END AS DOMAIN,


            COUNT(*) AS ISSUES



        FROM {ISSUE_TABLE}



        GROUP BY


            CASE


                WHEN ISSUE_TYPE LIKE '%Customer%'

                THEN 'Customer'


                WHEN ISSUE_TYPE LIKE '%Product%'

                THEN 'Product'


                ELSE 'Other'


            END



        ORDER BY ISSUES DESC



    """)

# -----------------------------------------------------------------------
# Sales impact calculation
# -----------------------------------------------------------------------

def load_sales_impact():

    return run_query(f"""

        WITH affected_objects AS (


            SELECT DISTINCT


                SOURCE_OBJECT_ID,


                ISSUE_TYPE



            FROM {ISSUE_TABLE}



            WHERE STATUS <> 'Rejected'


        )



        SELECT


            COUNT(DISTINCT s.CUSTOMER_BILL_TO_ID)

                AS CUSTOMERS_IMPACTED,



            SUM(s.SALES_AMOUNT_GROUP)

                AS SALES_IMPACT



        FROM {SALES_TABLE} s



        INNER JOIN affected_objects i



            ON s.CUSTOMER_BILL_TO_ID = i.SOURCE_OBJECT_ID



        WHERE s.SOURCE <> 'BUDGET'


          AND s.SALES_AMOUNT_GROUP <> 0



    """)
# -----------------------------------------------------------------------
# Recent issues
# -----------------------------------------------------------------------

def load_recent_issues():

    return run_query(f"""

        SELECT


            ISSUE_TYPE,


            SOURCE_OBJECT_ID,


            SOURCE_OBJECT_NAME,


            STATUS,


            OWNER,


            CREATED_DATE,


            UPDATED_DATE



        FROM {ISSUE_TABLE}



        ORDER BY CREATED_DATE DESC



        LIMIT 20



    """)
# -----------------------------------------------------------------------
# Render Overview Page
# -----------------------------------------------------------------------

def render():


    st.title(

        "📊 Data Quality Overview"

    )


    info_box(

        """
        Overview of data quality issues, business impact,
        and remediation progress across Customer and Product domains.
        """

    )


    # ---------------------------------------------------------------
    # KPI Cards
    # ---------------------------------------------------------------

    kpi = load_issue_kpis()



    if not kpi.empty:


        row = kpi.iloc[0]



        c1, c2, c3, c4 = st.columns(4)



        c1.metric(

            "Total Issues",

            f"{row['TOTAL_ISSUES']:,}"

        )



        c2.metric(

            "🟡 Open",

            f"{row['OPEN_ISSUES']:,}"

        )



        c3.metric(

            "🔵 Investigation",

            f"{row['INVESTIGATION_ISSUES']:,}"

        )



        c4.metric(

            "🟢 Resolved",

            f"{row['RESOLVED_ISSUES']:,}"

        )


    st.markdown("---")


    # ---------------------------------------------------------------
    # Business Impact
    # ---------------------------------------------------------------

    section_header(

        "💰 Business Impact"

    )


    impact = load_sales_impact()



    if not impact.empty:


        impact_row = impact.iloc[0]



        c1, c2 = st.columns(2)



        c1.metric(

            "Customers Impacted",

            f"{impact_row['CUSTOMERS_IMPACTED']:,}"

        )



        c2.metric(

            "Sales Impact",

            f"{impact_row['SALES_IMPACT']:,.0f}"

        )



    else:


        st.info(

            "No sales impact identified."

        )


    st.markdown("---")

    # ---------------------------------------------------------------
    # Issues by Data Domain
    # ---------------------------------------------------------------

    section_header(

        "📌 Issues by Data Domain"

    )


    domain_df = load_domain_summary()



    if not domain_df.empty:


        fig = px.bar(

            domain_df,

            x="DOMAIN",

            y="ISSUES",

            labels={

                "DOMAIN": "",

                "ISSUES": "Number of Issues"

            },

            title="Data Quality Issues by Domain"

        )


        fig.update_layout(

            height=300,

            margin=dict(

                t=40,

                b=20,

                l=20,

                r=20

            )

        )


        st.plotly_chart(

            fig,

            use_container_width=True

        )


    else:


        st.info(

            "No issue domains found."

        )


    st.markdown("---")



    # ---------------------------------------------------------------
    # Recent Issues
    # ---------------------------------------------------------------

    section_header(

        "🔍 Recent Issues"

    )


    recent = load_recent_issues()



    if not recent.empty:


        st.caption(

            f"{len(recent)} most recent issues"

        )


        st.dataframe(

            recent,

            use_container_width=True

        )


    else:


        st.success(

            "No recent issues found."

        )