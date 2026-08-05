from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from db import run_query
from ui import section_header, info_box


# -----------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------

BASELINE_DATE = "2026-03-11"


CUSTOMER_GROUP_TABLE = (
    "dev_datalake.bronze.web_app_chg_customer_group"
)


ISSUE_TABLE = (
    "dev_datalake.bronze.dq_issue_tracking"
)


ISSUE_HISTORY_TABLE = (
    "dev_datalake.bronze.dq_issue_history"
)


SALES_TABLE = (
    "dev_datalake.gold.f_sales_ledger_combined_full"
)



CHG_TABLES = {

    "Customer Group": {

        "table": CUSTOMER_GROUP_TABLE,

        "id_col": "RECORD_ID",

        "desc_col": "RECORD_NAME",

        "before": "VALUE_BEFORE",

        "after": "VALUE_AFTER"

    }

}

CUSTOMER_MASTER_TABLE = (
    "dev_datalake.silver.d_sales_customer"
)


STATUS_OPTIONS = [

    "Open",

    "Under Investigation",

    "Resolved",

    "Rejected",

    "Accepted Exception"

]



# -----------------------------------------------------------------------
# SQL helper
# -----------------------------------------------------------------------

def escape_sql(value):

    if value is None:

        return ""

    return str(value).replace(
        "'",
        "''"
    )



# -----------------------------------------------------------------------
# Create missing issues automatically
# -----------------------------------------------------------------------

def create_missing_issues():

    try:

        run_query(f"""

            MERGE INTO {ISSUE_TABLE} AS target


            USING (
            SELECT

        CONCAT(

            'CG_',

            RECORD_ID,

            '_',

                ROW_NUMBER() OVER (

                PARTITION BY RECORD_ID

                ORDER BY CHANGE_DATE

            )

        ) AS ISSUE_ID,

                    'DQC_CUSTOMER_GROUP' AS DQ_CHECK_ID,


                    'Customer Group Change' AS ISSUE_TYPE,


                    RECORD_ID AS SOURCE_OBJECT_ID,


                    RECORD_NAME AS SOURCE_OBJECT_NAME



                FROM {CUSTOMER_GROUP_TABLE}



                WHERE CHANGE_DATE > '{BASELINE_DATE}'



            ) source



            ON target.ISSUE_ID = source.ISSUE_ID



            WHEN NOT MATCHED THEN INSERT

            (

                ISSUE_ID,

                DQ_CHECK_ID,

                ISSUE_TYPE,

                SOURCE_OBJECT_ID,

                SOURCE_OBJECT_NAME,

                STATUS,

                COMMENT,

                OWNER,

                CREATED_DATE,

                UPDATED_DATE

            )


            VALUES

            (

                source.ISSUE_ID,

                source.DQ_CHECK_ID,

                source.ISSUE_TYPE,

                source.SOURCE_OBJECT_ID,

                source.SOURCE_OBJECT_NAME,

                'Open',

                '',

                '',

                current_timestamp(),

                current_timestamp()

            )


        """)


        return True


    except Exception as e:


        st.error(

            f"Could not create issues: {e}"

        )


        return False



# -----------------------------------------------------------------------
# Update issue status + history
# -----------------------------------------------------------------------

def update_issue_status(

    issue_id,

    status,

    comment,

    owner

):

    try:


        if status == "Resolved" and not comment.strip():

            st.warning(

                "Resolution comment is required."

            )

            return False



        safe_comment = escape_sql(comment)

        safe_owner = escape_sql(owner)



        # Get current status

        current = run_query(f"""

            SELECT STATUS

            FROM {ISSUE_TABLE}

            WHERE ISSUE_ID = '{issue_id}'


        """)



        old_status = "Open"



        if not current.empty:

            old_status = current.iloc[0]["STATUS"]



        # Update current issue

        run_query(f"""

            UPDATE {ISSUE_TABLE}


            SET


                STATUS = '{status}',


                COMMENT = '{safe_comment}',


                OWNER = '{safe_owner}',


                UPDATED_DATE = current_timestamp(),


                UPDATED_BY = current_user(),



                RESOLUTION_DATE =

                    CASE

                        WHEN '{status}' = 'Resolved'

                        THEN current_timestamp()

                        ELSE NULL

                    END



            WHERE ISSUE_ID = '{issue_id}'


        """)



        # Insert history record

        run_query(f"""

            INSERT INTO {ISSUE_HISTORY_TABLE}

            (

                ISSUE_HISTORY_ID,

                ISSUE_ID,

                OLD_STATUS,

                NEW_STATUS,

                COMMENT,

                OWNER,

                CHANGED_BY,

                CHANGED_DATE

            )


            SELECT

                uuid(),

                '{issue_id}',

                '{old_status}',

                '{status}',

                '{safe_comment}',

                '{safe_owner}',

                current_user(),

                current_timestamp()


        """)



        return True



    except Exception as e:


        st.error(

            f"Could not update issue: {e}"

        )


        return False

# -----------------------------------------------------------------------
# Change trend chart
# -----------------------------------------------------------------------

def _changes_chart(

    date_from_str,

    date_to_str

):

    try:

        df = run_query(f"""

            SELECT


                DATE(c.CHANGE_DATE) AS CHANGE_DATE,


                COALESCE(

                    i.STATUS,

                    'Open'

                ) AS STATUS,


                COUNT(*) AS ISSUES



            FROM {CUSTOMER_GROUP_TABLE} c



        LEFT JOIN {ISSUE_TABLE} i

            ON CONCAT(

                'CG_',

                c.RECORD_ID,

                '_',

                DATE_FORMAT(

                    c.CHANGE_DATE,

                    'yyyyMMddHHmmss'

                )

            ) = i.ISSUE_ID



            GROUP BY


                DATE(c.CHANGE_DATE),


                COALESCE(

                    i.STATUS,

                    'Open'

                )



            ORDER BY DATE(c.CHANGE_DATE)



        """)



        if df.empty:

            return None



        df["CHANGE_DATE"] = pd.to_datetime(

            df["CHANGE_DATE"]

        ).dt.date



        fig = px.bar(

            df,

            x="CHANGE_DATE",

            y="ISSUES",

            color="STATUS",

            barmode="stack",

            labels={

                "CHANGE_DATE": "",

                "ISSUES": "Number of Issues",

                "STATUS": "Status"

            },

            title="Customer Group Issues Over Time"

        )


        fig.update_layout(

            height=350,

            margin=dict(

                t=40,

                b=20,

                l=20,

                r=20

            )

        )


        return fig



    except Exception as e:


        st.warning(

            f"Could not load issue trend chart: {e}"

        )


        return None



# -----------------------------------------------------------------------
# Load customer group issues
# -----------------------------------------------------------------------

def load_customer_group_issues(

    date_from_str,

    date_to_str

):

    try:


        log = run_query(f"""

            WITH customer_changes AS (

                SELECT


                    CONCAT(

        'CG_',

        RECORD_ID,

        '_',

        ROW_NUMBER() OVER (

            PARTITION BY RECORD_ID

            ORDER BY CHANGE_DATE

        )

    ) AS ISSUE_ID,

                    CHANGE_DATE,


                    RECORD_ID,


                    RECORD_NAME,


                    VALUE_BEFORE,


                    VALUE_AFTER



                FROM {CUSTOMER_GROUP_TABLE}



                WHERE CHANGE_DATE > '{BASELINE_DATE}'


                  AND CHANGE_DATE >= '{date_from_str}'


                  AND CHANGE_DATE <= '{date_to_str}'


            ),



            sales_history AS (

                SELECT


                    CUSTOMER_BILL_TO_ID AS CUSTOMER_ID,



                    MAX(

                        CASE

                            WHEN ACCOUNTING_YEAR = 2026

                            THEN 1

                            ELSE 0

                        END

                    ) AS HAS_2026_SALES,



                    MAX(

                        CASE

                            WHEN ACCOUNTING_YEAR < 2026

                            THEN 1

                            ELSE 0

                        END

                    ) AS HAS_OTHER_YEAR_SALES,



                    MIN(ACCOUNTING_YEAR) AS FIRST_SALES_YEAR,


                    MAX(ACCOUNTING_YEAR) AS LAST_SALES_YEAR



                FROM {SALES_TABLE}



                WHERE SOURCE <> 'BUDGET'


                  AND SALES_AMOUNT_GROUP <> 0



                GROUP BY CUSTOMER_BILL_TO_ID

            )



            SELECT


                c.ISSUE_ID,


                c.CHANGE_DATE,


                c.RECORD_ID,


                c.RECORD_NAME,


                c.VALUE_BEFORE AS GROUP_BEFORE,


                c.VALUE_AFTER AS GROUP_AFTER,



                CASE


                    WHEN s.HAS_2026_SALES = 1

                     AND s.HAS_OTHER_YEAR_SALES = 0


                    THEN 'Sales in 2026 only'



                    WHEN s.HAS_OTHER_YEAR_SALES = 1


                    THEN 'Sales in other years'



                    ELSE 'No sales history'



                END AS SALES_STATUS,



                s.FIRST_SALES_YEAR,


                s.LAST_SALES_YEAR,



                COALESCE(

                    i.STATUS,

                    'Open'

                ) AS STATUS,



                COALESCE(

                    i.OWNER,

                    ''

                ) AS OWNER,



                COALESCE(

                    i.COMMENT,

                    ''

                ) AS COMMENT,



                i.CREATED_DATE,


                i.UPDATED_DATE,


                i.RESOLUTION_DATE



            FROM customer_changes c



            LEFT JOIN sales_history s


                ON c.RECORD_ID = s.CUSTOMER_ID



            LEFT JOIN {ISSUE_TABLE} i


                ON c.ISSUE_ID = i.ISSUE_ID



            ORDER BY


                c.CHANGE_DATE DESC



            LIMIT 2000



        """)



        return log



    except Exception as e:


        st.error(

            f"Could not load customer group issues: {e}"

        )


        return pd.DataFrame()

# -----------------------------------------------------------------------
# Issue management detail view
# -----------------------------------------------------------------------

def render_change_log_detail(
    cfg,

    date_from_str,

    date_to_str

):


    section_header(

        "🔍 Customer Group Issue Management"

    )



    log = load_customer_group_issues(

        date_from_str,

        date_to_str

    )



    if log.empty:


        st.success(

            "✅ No Customer Group issues found."

        )

        return



    # ----------------------------------------------------
    # KPI cards
    # ----------------------------------------------------

    total_issues = len(log)



    open_count = (

        log["STATUS"]

        == "Open"

    ).sum()



    investigation_count = (

        log["STATUS"]

        == "Under Investigation"

    ).sum()



    resolved_count = (

        log["STATUS"]

        == "Resolved"

    ).sum()



    k1, k2, k3, k4 = st.columns(4)



    k1.metric(

        "Total Issues",

        f"{total_issues:,}"

    )


    k2.metric(

        "🟡 Open",

        f"{open_count:,}"

    )


    k3.metric(

        "🔵 Investigation",

        f"{investigation_count:,}"

    )


    k4.metric(

        "🟢 Resolved",

        f"{resolved_count:,}"

    )



    st.markdown("---")



    # ----------------------------------------------------
    # Format values
    # ----------------------------------------------------

    display = log.copy()



    display["CHANGE_DATE"] = (

        pd.to_datetime(

            display["CHANGE_DATE"]

        )

        .dt.strftime("%Y-%m-%d")

    )



    st.caption(

        f"{len(display):,} issues displayed"

    )



    # ----------------------------------------------------
    # Issue cards
    # ----------------------------------------------------

    for _, row in display.iterrows():


        with st.expander(

            f"🔎 {row['RECORD_NAME']} "
            f"({row['RECORD_ID']}) "
            f"- {row['STATUS']}"

        ):



            col1, col2 = st.columns(2)



            with col1:


                st.markdown(

                    f"""

**Issue ID**  
{row['ISSUE_ID']}


**Change Date**  
{row['CHANGE_DATE']}


**Previous Value**  
{row['GROUP_BEFORE']}


**New Value**  
{row['GROUP_AFTER']}

"""

                )



            with col2:


                st.markdown(

                    f"""

**Sales Impact**  
{row['SALES_STATUS']}


**First Sales Year**  
{row['FIRST_SALES_YEAR']}


**Last Sales Year**  
{row['LAST_SALES_YEAR']}


**Created**  
{row['CREATED_DATE']}

"""

                )



            st.markdown("---")



            current_status = row["STATUS"]



            current_owner = (

                row["OWNER"]

                if pd.notna(row["OWNER"])

                else ""

            )



            current_comment = (

                row["COMMENT"]

                if pd.notna(row["COMMENT"])

                else ""

            )



            c1, c2 = st.columns(2)



            with c1:


                new_status = st.selectbox(

                    "Status",

                    STATUS_OPTIONS,

                    index=STATUS_OPTIONS.index(

                        current_status

                    ),

                    key=f"status_{row['ISSUE_ID']}"

                )



            with c2:


                new_owner = st.text_input(

                    "Owner",

                    value=current_owner,

                    key=f"owner_{row['ISSUE_ID']}"

                )



            new_comment = st.text_area(

                "Comment",

                value=current_comment,

                key=f"comment_{row['ISSUE_ID']}"

            )



            if st.button(

                "💾 Save Changes",

                key=f"save_{row['ISSUE_ID']}"

            ):



                result = update_issue_status(

                    issue_id=row["ISSUE_ID"],

                    status=new_status,

                    comment=new_comment,

                    owner=new_owner

                )



                if result:


                    st.success(

                        "Issue updated successfully."

                    )


                    st.rerun()

# -----------------------------------------------------------------------
# Main page render
# -----------------------------------------------------------------------

def render():


    # Create missing issues first

    create_missing_issues()



    st.title(

        "📅 Customer Group Change Tracking"

    )



    info_box(f"Customer Group changes detected from the snapshot comparison table.Baseline date <b>{BASELINE_DATE}</b> is excluded.Only records changed after the baseline load are displayed.")




    # ----------------------------------------------------
    # Date filters
    # ----------------------------------------------------

    today = date.today()


    baseline = date.fromisoformat(

        BASELINE_DATE

    )



    PRESETS = {


        "All time (since baseline)": (

            baseline + timedelta(days=1),

            today

        ),


        "Last 7 days": (

            today - timedelta(days=7),

            today

        ),


        "Last 14 days": (

            today - timedelta(days=14),

            today

        ),


        "Last 30 days": (

            today - timedelta(days=30),

            today

        ),


        "Custom": None


    }



    c1, c2, c3 = st.columns(

        [2, 2, 2]

    )



    with c1:


        preset = st.selectbox(

            "Date range",

            list(PRESETS.keys()),

            key="cg_date_range"

        )



    if PRESETS[preset] is not None:


        date_from, date_to = PRESETS[preset]



        with c2:


            st.caption(

                f"**{date_from}** → **{date_to}**"

            )



    else:


        with c2:


            date_from = st.date_input(

                "From",

                value=baseline + timedelta(days=1),

                min_value=baseline + timedelta(days=1),

                max_value=today,

                key="cg_from"

            )



        with c3:


            date_to = st.date_input(

                "To",

                value=today,

                min_value=baseline + timedelta(days=1),

                max_value=today,

                key="cg_to"

            )



    date_from_str = str(date_from)


    date_to_str = str(date_to)



    st.markdown("---")



    # ----------------------------------------------------
    # Trend chart
    # ----------------------------------------------------

    section_header(

        f"📈 Customer Group Changes · "
        f"{date_from_str} → {date_to_str}"

    )



    fig = _changes_chart(

        date_from_str,

        date_to_str

    )



    if fig:


        st.plotly_chart(

            fig,

            use_container_width=True

        )


        # Customer Record Details
    section_header(
        "👤 Customer Record Details"
    )

    try:

        customers = run_query(f"""

            SELECT DISTINCT

                c.CUSTOMER_ID,

                c.CUSTOMER_DESC,

                c.CUSTOMER_GROUP_DESC,

                c.CUSTOMER_TYPE,

                c.COUNTRY_UID,

                c.MAGNITUDE_CODE,

                c.INTERCO,

                c.SALES_TEAM,

                c.SOURCE,

                c.LAST_UPDATED,

                i.STATUS,

                i.OWNER,

                i.COMMENT


            FROM {CUSTOMER_MASTER_TABLE} c


            INNER JOIN {CUSTOMER_GROUP_TABLE} ch

                ON c.CUSTOMER_ID = ch.RECORD_ID


            INNER JOIN {ISSUE_TABLE} i

                ON CONCAT(

                    'CG_',

                    ch.RECORD_ID,

                    '_',

                    DATE_FORMAT(

                        ch.CHANGE_DATE,

                        'yyyyMMddHHmmss'

                    )

                ) = i.ISSUE_ID



            WHERE ch.CHANGE_DATE > '{BASELINE_DATE}'


            AND ch.CHANGE_DATE >= '{date_from_str}'


            AND ch.CHANGE_DATE <= '{date_to_str}'


            AND i.STATUS IN (

                    'Open',

                    'Under Investigation'

            )


            ORDER BY c.CUSTOMER_DESC


            LIMIT 500


        """)


        st.dataframe(
            customers,
            use_container_width=True
        )


    except Exception as e:

        st.error(
            f"Could not load customer records: {e}"
        )


    # Issue Management
    cfg = CHG_TABLES["Customer Group"]

    render_change_log_detail(
        cfg,
        date_from_str,
        date_to_str
    )