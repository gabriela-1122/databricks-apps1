"""
customer_exceptions.py — Market Segment customer exclusion config
============================================================
Centralised list of customer IDs / patterns excluded from the
Market Segment unallocated list and the Market Segment mapping
rate KPI in the Overview.

HOW TO ADD EXCEPTIONS
---------------------
1.  Add the exact CUSTOMER_BILL_TO_ID to EXCLUDED_CUSTOMER_IDS.
2.  Add any LIKE patterns (SQL wildcards) to EXCLUDED_CUSTOMER_PATTERNS.
3.  Re-deploy the app — both cust_market_segment.py and overview.py
    import from this file, so one change covers everywhere.

WHY EXCLUDE THESE CUSTOMERS
----------------------------
- Dummy / catch-all accounts used by ERPs (no real commercial activity)
- System accounts that are never mapped to a market segment by design
- Accounts shared across multiple entities where segment assignment is
  not meaningful

These are excluded from the unallocated list (they would generate noise)
and from the mapping rate denominator (they would deflate the %).
"""

# ── Exact customer IDs to exclude (case-sensitive, as stored in the ERP) ─────
EXCLUDED_CUSTOMER_IDS: list[str] = [
    "999999",        # Generic / catch-all customer (multiple ERPs)
    "0000900000",    # SAP dummy customer
    "2003",          # System account
    "70006009",      # HWI internal account
    "2364622",
    "C11547",
    "0000900000",
    "DUMMY_01",
    "DUMMY_02",
    "DUMMY_03",
    "DUMMY_04",
    "DUMMY_05",
    "DUMMY_06",
    "DUMMY_08",
    "DUMMY_09",
    "DUMMY_10",
    "DUMMY_11",
    "2003",
    "2004",
    "70004492",
    "70006009",
    "No Customer",
    "TBD31",
    "C1063101",
    "70004169",
    "2237126",
    "0000999999",
    ""
]

# ── SQL LIKE patterns to exclude (% = any sequence of characters) ─────────────
EXCLUDED_CUSTOMER_PATTERNS: list[str] = [
    "DUMMY%",        # All accounts whose ID starts with DUMMY
]


# ── SQL clause builders ───────────────────────────────────────────────────────
# Use these in queries — they return a ready-to-append WHERE fragment.

def ms_exclusion_clause(id_column: str = "CUSTOMER_BILL_TO_ID") -> str:
    """
    Returns a SQL fragment (starting with AND) that excludes all
    configured dummy/system customers.

    Parameters
    ----------
    id_column : str
        The column reference in the calling query, e.g.
        'fsl.CUSTOMER_BILL_TO_ID', 'ar.CUSTOMER_ID', 'sc.CUSTOMER_ID'.

    Example
    -------
    >>> ms_exclusion_clause("fsl.CUSTOMER_BILL_TO_ID")
    "AND fsl.CUSTOMER_BILL_TO_ID NOT IN ('999999','0000900000','2003','70006009')
     AND fsl.CUSTOMER_BILL_TO_ID NOT LIKE 'DUMMY%'
     AND fsl.CUSTOMER_BILL_TO_ID IS NOT NULL"
    """
    parts = []

    if EXCLUDED_CUSTOMER_IDS:
        ids_sql = ", ".join(f"'{cid}'" for cid in EXCLUDED_CUSTOMER_IDS)
        parts.append(f"AND {id_column} NOT IN ({ids_sql})")

    for pattern in EXCLUDED_CUSTOMER_PATTERNS:
        parts.append(f"AND {id_column} NOT LIKE '{pattern}'")

    parts.append(f"AND {id_column} IS NOT NULL")

    return "\n    ".join(parts)


def ms_inclusion_clause(id_column: str = "CUSTOMER_BILL_TO_ID") -> str:
    """
    Returns the inverse SQL fragment — matches only the excluded customers.
    Useful for auditing / reporting on excluded accounts.
    """
    parts = []

    conditions = []
    if EXCLUDED_CUSTOMER_IDS:
        ids_sql = ", ".join(f"'{cid}'" for cid in EXCLUDED_CUSTOMER_IDS)
        conditions.append(f"{id_column} IN ({ids_sql})")
    for pattern in EXCLUDED_CUSTOMER_PATTERNS:
        conditions.append(f"{id_column} LIKE '{pattern}'")

    if conditions:
        parts.append("AND (" + "\n       OR ".join(conditions) + ")")

    return "\n    ".join(parts)


def ms_mapped_inclusion_expr(id_column: str = "CUSTOMER_BILL_TO_ID",
                              segment_column: str = "MARKET_ID_NEW") -> str:
    """
    Returns a CASE WHEN expression that counts a transaction as 'mapped'
    if it either has a segment OR belongs to an excluded (dummy) customer.

    Use this in the numerator of the mapping rate KPI so that dummy
    customers don't deflate the overall percentage.

    Example (Sales Ledger):
        SUM(CASE WHEN {ms_mapped_inclusion_expr('fsl.CUSTOMER_BILL_TO_ID','fsl.MARKET_ID_NEW')}
                 THEN ABS(fsl.SALES_AMOUNT_GROUP) ELSE 0 END)
    """
    id_conditions = []
    if EXCLUDED_CUSTOMER_IDS:
        ids_sql = ", ".join(f"'{cid}'" for cid in EXCLUDED_CUSTOMER_IDS)
        id_conditions.append(f"{id_column} IN ({ids_sql})")
    for pattern in EXCLUDED_CUSTOMER_PATTERNS:
        id_conditions.append(f"{id_column} LIKE '{pattern}'")
    id_conditions.append(f"{id_column} IS NULL")

    id_part = "\n       OR ".join(id_conditions)

    return (
        f"({segment_column} IS NOT NULL\n"
        f"        AND TRIM(CAST({segment_column} AS STRING)) <> '')\n"
        f"       OR {id_part}"
    )
