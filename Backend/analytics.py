"""
analytics.py — Advanced analytical endpoints (NetVerify)
Project: NetVerify — Tunisie Telecom

This module gathers the analyses that go beyond counting: distributions,
percentiles, correlations, moving averages, cross matrices, Pareto diagram and
data-quality controls.

Three principles hold the whole file together:

1. **The computation stays in the database.** Percentiles (`percentile_cont`),
   histograms (`width_bucket`), moving averages (`AVG() OVER`), cumulative
   shares (`SUM() OVER (ORDER BY …)`) and correlations (`corr`) are executed by
   PostgreSQL. The front-end receives series ready to plot, never 20,000 rows
   to aggregate in the browser.
2. **No implicit denominator.** Every rate is returned with its population: the
   SNR margin is only populated on 68% of the measurements (GPON produces
   none), so a "% of lines below the threshold" computed against the total
   number of measurements would be false. The endpoints return
   `nb_mesures_evaluees` next to each counter.
3. **The thresholds are the verification engine's thresholds.** SNR < 6 dB,
   attenuation > 40 dB, 90% rate tolerance: these are the rules of
   `comparator.py`. The analysis and the D+14 control deliver the same verdict.

Mounted in `main.py` by `app.include_router(analytics.router)`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import SessionLocal
from comparator import TOLERANCE_THRESHOLD

# ══════════════════════════════════════════════════
# TECHNICAL THRESHOLDS
# ══════════════════════════════════════════════════
# Aligned with `determiner_cause_probable()` in comparator.py, where they are
# written out in the tests. They are named here so that the analysis and the
# diagnosis cannot diverge silently.
SNR_MIN_DB = 6.0
ATTENUATION_MAX_DB = 40.0

# Scatter-plot sampling: 1 measurement in 12 (~1,100 points out of 14,000).
# Deterministic (modulo on the primary key) rather than random, so that two
# successive loads display exactly the same cloud.
SAMPLE_STEP = 12

router = APIRouter(tags=["analytics"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _rows(db: Session, sql: str, **params: Any) -> list:
    return db.execute(text(sql), params).fetchall()


def _number(value: Any, defaut: float = 0.0) -> float:
    """Normalises PostgreSQL Decimal/None values into JSON-serialisable floats."""
    return defaut if value is None else float(value)


# ══════════════════════════════════════════════════
# SHARED SQL BLOCK — subscribed profile per line
# ══════════════════════════════════════════════════
# The subscribed rate is stored as text on the work order ("20 mbps"). It is
# aggregated per line number BEFORE any join: a customer carrying two work
# orders would otherwise duplicate each of their measurements, and every
# population count would be wrong.
PROFILE_CTE = """
    profil AS (
        SELECT num_appel,
               MAX(NULLIF(regexp_replace(debit, '[^0-9]', '', 'g'), '')::int) AS mbps_souscrits
        FROM reclamations_workflow
        WHERE debit IS NOT NULL
        GROUP BY num_appel
    )
"""


# ══════════════════════════════════════════════════
# 1. LINE QUALITY
# ══════════════════════════════════════════════════

@router.get("/stats/quality/summary")
def get_quality_summary(db: Session = Depends(get_db)):
    """Headline indicators of the "Line quality" page.

    Correlations are returned exactly as measured, including when they are
    null: an absence of link between attenuation and rate is a result, not a
    missing value.
    """
    row = _rows(db, f"""
        WITH {PROFILE_CTE}
        SELECT
            COUNT(*)                                              AS nb_mesures,
            COUNT(DISTINCT m.num_appel)                           AS nb_lignes,
            COUNT(m.line_snr_margin_down)                         AS nb_snr,
            COUNT(*) FILTER (WHERE m.line_snr_margin_down < :snr) AS nb_snr_sous_seuil,
            COUNT(m.line_attenuation_down)                        AS nb_attenuation,
            COUNT(*) FILTER (WHERE m.line_attenuation_down > :att) AS nb_attenuation_haute,
            COUNT(*) FILTER (WHERE m.channel_rate_kbps = 0)       AS nb_debit_nul,
            COUNT(*) FILTER (WHERE m.status_training ILIKE '%Idle%') AS nb_coupures,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY m.channel_rate_kbps) AS debit_median_kbps,
            AVG(m.line_snr_margin_down)                           AS snr_moyen,
            AVG(m.line_attenuation_down)                          AS attenuation_moyenne,
            corr(m.line_attenuation_down, m.channel_rate_kbps)    AS corr_attenuation_debit,
            corr(m.line_snr_margin_down, m.line_attenuation_down) AS corr_snr_attenuation,
            COUNT(*) FILTER (
                WHERE p.mbps_souscrits IS NOT NULL
                  AND m.channel_rate_kbps < p.mbps_souscrits * 1024 * :tolerance
            )                                                     AS nb_sous_profil,
            COUNT(*) FILTER (WHERE p.mbps_souscrits IS NOT NULL)  AS nb_profil_connu
        FROM mesures_netscan m
        LEFT JOIN profil p ON p.num_appel = m.num_appel
    """, snr=SNR_MIN_DB, att=ATTENUATION_MAX_DB, tolerance=TOLERANCE_THRESHOLD)[0]

    return {
        "nb_mesures": row[0],
        "nb_lignes": row[1],
        "nb_snr_evalue": row[2],
        "nb_snr_sous_seuil": row[3],
        "nb_attenuation_evaluee": row[4],
        "nb_attenuation_haute": row[5],
        "nb_debit_nul": row[6],
        "nb_coupures": row[7],
        "debit_median_kbps": _number(row[8]),
        "snr_moyen": round(_number(row[9]), 2),
        "attenuation_moyenne": round(_number(row[10]), 2),
        "corr_attenuation_debit": round(_number(row[11]), 3),
        "corr_snr_attenuation": round(_number(row[12]), 3),
        "nb_sous_profil": row[13],
        "nb_profil_connu": row[14],
        "seuil_snr_db": SNR_MIN_DB,
        "seuil_attenuation_db": ATTENUATION_MAX_DB,
        "tolerance_debit": TOLERANCE_THRESHOLD,
    }


# Metrics exposed to the histogram.
#
# `expression`, `borne_min`, `borne_max` and `paliers` NEVER come from the HTTP
# request: the `metric` parameter is only used as a key into this dictionary.
# No SQL expression can therefore be injected by the caller, and the bounds of a
# histogram stay stable between calls.
DISTRIBUTION_METRICS: dict[str, dict[str, Any]] = {
    "snr": {
        "expression": "m.line_snr_margin_down",
        "libelle": "Downstream signal-to-noise margin (SNR)",
        "unite": " dB",
        "borne_min": 0.0,
        "borne_max": 36.0,
        "paliers": 18,
        "seuil": SNR_MIN_DB,
        "seuil_libelle": "Instability threshold",
        # Below the threshold = bad: the risk zone is on the left.
        "sens": "minimum",
    },
    "attenuation": {
        "expression": "m.line_attenuation_down",
        "libelle": "Downstream line attenuation",
        "unite": " dB",
        "borne_min": 0.0,
        "borne_max": 50.0,
        "paliers": 25,
        "seuil": ATTENUATION_MAX_DB,
        "seuil_libelle": "Degraded cable",
        "sens": "maximum",
    },
    "restitution": {
        # Measured rate relative to the subscribed rate. This is the only one of
        # the three metrics comparable across technologies: 10, 20 and 100 Mb/s
        # brought back to the same 0-120% scale.
        "expression": "m.channel_rate_kbps / (p.mbps_souscrits * 1024.0) * 100",
        "libelle": "Delivery ratio against the subscribed rate",
        "unite": " %",
        "borne_min": 0.0,
        "borne_max": 120.0,
        "paliers": 24,
        "seuil": TOLERANCE_THRESHOLD * 100,
        "seuil_libelle": "D+14 tolerance",
        "sens": "minimum",
    },
}


@router.get("/stats/quality/distribution")
def get_distribution(
    metric: str = Query("snr", description="snr | attenuation | restitution"),
    db: Session = Depends(get_db),
):
    """Histogram of a NetScan metric, computed by `width_bucket`.

    Out-of-range values are folded back into the extreme bucket rather than
    discarded: the total of the buckets always equals the announced population.
    """
    config = DISTRIBUTION_METRICS.get(metric)
    if config is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown metric: {metric}. "
                   f"Accepted values: {', '.join(DISTRIBUTION_METRICS)}.",
        )

    expression = config["expression"]
    width = (config["borne_max"] - config["borne_min"]) / config["paliers"]

    rows = _rows(db, f"""
        WITH {PROFILE_CTE},
        valeurs AS (
            SELECT LEAST(GREATEST({expression}, :borne_min), :borne_max) AS valeur
            FROM mesures_netscan m
            LEFT JOIN profil p ON p.num_appel = m.num_appel
            WHERE {expression} IS NOT NULL
        )
        SELECT
            width_bucket(valeur, :borne_min, :borne_max, :paliers) AS palier,
            COUNT(*)                                               AS nb,
            COUNT(*) * 100.0 / SUM(COUNT(*)) OVER ()               AS part
        FROM valeurs
        GROUP BY palier
        ORDER BY palier
    """, borne_min=config["borne_min"], borne_max=config["borne_max"],
         paliers=config["paliers"])

    stats = _rows(db, f"""
        WITH {PROFILE_CTE},
        valeurs AS (
            SELECT {expression} AS valeur
            FROM mesures_netscan m
            LEFT JOIN profil p ON p.num_appel = m.num_appel
            WHERE {expression} IS NOT NULL
        )
        SELECT COUNT(*), AVG(valeur), STDDEV_SAMP(valeur),
               percentile_cont(0.10) WITHIN GROUP (ORDER BY valeur),
               percentile_cont(0.50) WITHIN GROUP (ORDER BY valeur),
               percentile_cont(0.90) WITHIN GROUP (ORDER BY valeur),
               COUNT(*) FILTER (WHERE valeur < :seuil),
               COUNT(*) FILTER (WHERE valeur > :seuil)
        FROM valeurs
    """, seuil=config["seuil"])[0]

    # `width_bucket` returns `paliers + 1` for a value exactly equal to the
    # upper bound: it is folded back into the last full bucket.
    latest = config["paliers"]
    cumul: dict[int, int] = {}
    parts: dict[int, float] = {}
    for palier, nb, part in rows:
        index = min(max(int(palier), 1), latest)
        cumul[index] = cumul.get(index, 0) + nb
        parts[index] = parts.get(index, 0.0) + _number(part)

    paliers = [
        {
            "borne_min": round(config["borne_min"] + (index - 1) * width, 2),
            "borne_max": round(config["borne_min"] + index * width, 2),
            "centre": round(config["borne_min"] + (index - 0.5) * width, 2),
            "nb": cumul.get(index, 0),
            "part": round(parts.get(index, 0.0), 2),
        }
        for index in range(1, latest + 1)
    ]

    out_of_threshold = stats[6] if config["sens"] == "minimum" else stats[7]
    return {
        "metric": metric,
        "libelle": config["libelle"],
        "unite": config["unite"],
        "seuil": config["seuil"],
        "seuil_libelle": config["seuil_libelle"],
        "sens": config["sens"],
        "nb_mesures_evaluees": stats[0],
        "moyenne": round(_number(stats[1]), 2),
        "ecart_type": round(_number(stats[2]), 2),
        "p10": round(_number(stats[3]), 2),
        "mediane": round(_number(stats[4]), 2),
        "p90": round(_number(stats[5]), 2),
        "nb_hors_seuil": out_of_threshold,
        "paliers": paliers,
    }


@router.get("/stats/quality/percentiles")
def get_percentiles_by_technology(db: Session = Depends(get_db)):
    """Dispersion (P10 / median / P90) of the three metrics, per technology.

    An average alone would hide the estate's real problem: on GPON the median
    rate sits at nominal while the P10 collapses. It is the gap between the two
    that designates the lines to be dealt with.
    """
    rows = _rows(db, f"""
        WITH {PROFILE_CTE}
        SELECT
            c.techno_souscrite,
            COUNT(*)                        AS nb_mesures,
            COUNT(m.line_snr_margin_down)   AS nb_snr,
            percentile_cont(0.10) WITHIN GROUP (ORDER BY m.line_snr_margin_down) AS snr_p10,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY m.line_snr_margin_down) AS snr_p50,
            percentile_cont(0.90) WITHIN GROUP (ORDER BY m.line_snr_margin_down) AS snr_p90,
            percentile_cont(0.10) WITHIN GROUP (ORDER BY m.line_attenuation_down) AS att_p10,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY m.line_attenuation_down) AS att_p50,
            percentile_cont(0.90) WITHIN GROUP (ORDER BY m.line_attenuation_down) AS att_p90,
            percentile_cont(0.10) WITHIN GROUP (ORDER BY m.channel_rate_kbps) AS debit_p10,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY m.channel_rate_kbps) AS debit_p50,
            percentile_cont(0.90) WITHIN GROUP (ORDER BY m.channel_rate_kbps) AS debit_p90,
            MAX(p.mbps_souscrits) * 1024    AS debit_souscrit_kbps
        FROM mesures_netscan m
        JOIN clients c ON c.num_telephone = m.num_appel
        LEFT JOIN profil p ON p.num_appel = m.num_appel
        GROUP BY c.techno_souscrite
        ORDER BY c.techno_souscrite
    """)

    return [
        {
            "technologie": r[0],
            "nb_mesures": r[1],
            "nb_snr": r[2],
            "couverture_snr": round(r[2] * 100.0 / r[1], 1) if r[1] else 0.0,
            "snr_p10": round(_number(r[3]), 1),
            "snr_p50": round(_number(r[4]), 1),
            "snr_p90": round(_number(r[5]), 1),
            "attenuation_p10": round(_number(r[6]), 1),
            "attenuation_p50": round(_number(r[7]), 1),
            "attenuation_p90": round(_number(r[8]), 1),
            "debit_p10_kbps": round(_number(r[9]), 0),
            "debit_p50_kbps": round(_number(r[10]), 0),
            "debit_p90_kbps": round(_number(r[11]), 0),
            "debit_souscrit_kbps": round(_number(r[12]), 0),
        }
        for r in rows
    ]


@router.get("/stats/quality/scatter")
def get_diagnostic_scatter(db: Session = Depends(get_db)):
    """Attenuation x SNR margin scatter plot, sampled, with its risk quadrant.

    The engine's two thresholds cut the plane into four: the "high attenuation
    AND low SNR" quadrant isolates the physically degraded lines, the ones that
    simply re-dispatching an intervention will not fix.

    The quadrant counters cover the WHOLE population; only the plotted points
    are sampled.
    """
    points = _rows(db, """
        SELECT m.line_attenuation_down, m.line_snr_margin_down,
               m.channel_rate_kbps, c.techno_souscrite, m.status_training
        FROM mesures_netscan m
        JOIN clients c ON c.num_telephone = m.num_appel
        WHERE m.line_attenuation_down IS NOT NULL
          AND m.line_snr_margin_down IS NOT NULL
          AND MOD(m.id_mesure, :pas) = 0
    """, pas=SAMPLE_STEP)

    quadrants = _rows(db, """
        SELECT
            COUNT(*) FILTER (WHERE line_snr_margin_down <  :snr AND line_attenuation_down >  :att),
            COUNT(*) FILTER (WHERE line_snr_margin_down <  :snr AND line_attenuation_down <= :att),
            COUNT(*) FILTER (WHERE line_snr_margin_down >= :snr AND line_attenuation_down >  :att),
            COUNT(*) FILTER (WHERE line_snr_margin_down >= :snr AND line_attenuation_down <= :att),
            COUNT(*)
        FROM mesures_netscan
        WHERE line_attenuation_down IS NOT NULL AND line_snr_margin_down IS NOT NULL
    """, snr=SNR_MIN_DB, att=ATTENUATION_MAX_DB)[0]

    return {
        "seuil_snr_db": SNR_MIN_DB,
        "seuil_attenuation_db": ATTENUATION_MAX_DB,
        "pas_echantillon": SAMPLE_STEP,
        "nb_points_traces": len(points),
        "quadrants": {
            "degradee": quadrants[0],
            "snr_seul": quadrants[1],
            "attenuation_seule": quadrants[2],
            "conforme": quadrants[3],
            "total": quadrants[4],
        },
        "points": [
            {
                "attenuation": _number(p[0]),
                "snr": _number(p[1]),
                "debit_kbps": p[2],
                "technologie": p[3],
                "statut": p[4],
            }
            for p in points
        ],
    }


# ══════════════════════════════════════════════════
# 2. OPERATIONAL PERFORMANCE
# ══════════════════════════════════════════════════

@router.get("/stats/ops/backlog")
def get_backlog(db: Session = Depends(get_db)):
    """Age of the stock of unclosed work orders, per band.

    Age is counted from the most recent observation date in the referential,
    NOT from `now()`. The referential is a frozen extract: measured against the
    current clock, the entire stock would mechanically fall into the oldest
    band and the chart would teach nothing. The reference date is returned so
    it can be displayed with the chart.
    """
    reference = _rows(db, "SELECT MAX(date_etat) FROM reclamations_workflow")[0][0]
    if reference is None:
        return {"date_reference": None, "tranches": [], "total": 0}

    rows = _rows(db, """
        WITH ages AS (
            SELECT etat_ot,
                   -- Explicit CAST: the `:param::type` syntax is unreadable for
                   -- SQLAlchemy's parameter parser, which takes the second ":"
                   -- for the start of another parameter.
                   EXTRACT(DAY FROM (CAST(:reference AS timestamp) - date_etat))::int AS age
            FROM reclamations_workflow
            WHERE etat_ot <> 'Traite' AND date_etat IS NOT NULL
        )
        SELECT
            CASE WHEN age <= 7  THEN '0-7 d'
                 WHEN age <= 14 THEN '8-14 d'
                 WHEN age <= 30 THEN '15-30 d'
                 ELSE '30 d and over' END                   AS tranche,
            MIN(age)                                        AS rang,
            COUNT(*)                                        AS total,
            COUNT(*) FILTER (WHERE etat_ot = 'Emis')        AS emises,
            COUNT(*) FILTER (WHERE etat_ot = 'En cours')    AS en_cours,
            ROUND(AVG(age), 1)                              AS age_moyen
        FROM ages
        GROUP BY tranche
        ORDER BY rang
    """, reference=reference)

    global_ = _rows(db, """
        SELECT COUNT(*),
               ROUND(AVG(EXTRACT(DAY FROM (CAST(:reference AS timestamp) - date_etat))), 1),
               percentile_cont(0.5) WITHIN GROUP (
                   ORDER BY EXTRACT(DAY FROM (CAST(:reference AS timestamp) - date_etat))),
               MAX(EXTRACT(DAY FROM (CAST(:reference AS timestamp) - date_etat)))
        FROM reclamations_workflow
        WHERE etat_ot <> 'Traite' AND date_etat IS NOT NULL
    """, reference=reference)[0]

    return {
        "date_reference": reference.isoformat(),
        "total": global_[0],
        "age_moyen": _number(global_[1]),
        "age_median": _number(global_[2]),
        "age_max": _number(global_[3]),
        "tranches": [
            {
                "tranche": r[0],
                "total": r[2],
                "emises": r[3],
                "en_cours": r[4],
                "age_moyen": _number(r[5]),
            }
            for r in rows
        ],
    }


@router.get("/stats/ops/daily-flow")
def get_daily_flow(db: Session = Depends(get_db)):
    """Daily volume of status changes, smoothed by a 7-day moving average.

    The moving average is computed in SQL (`AVG() OVER … ROWS BETWEEN 6
    PRECEDING AND CURRENT ROW`). The first six days are therefore a partial
    average: they are flagged `partiel` so that the curve does not assert a
    trend it does not yet have the points to compute.
    """
    rows = _rows(db, """
        WITH jours AS (
            SELECT date_etat::date                            AS jour,
                   COUNT(*)                                   AS total,
                   COUNT(*) FILTER (WHERE etat_ot = 'Traite') AS traitees
            FROM reclamations_workflow
            WHERE date_etat IS NOT NULL
            GROUP BY 1
        )
        SELECT jour, total, traitees,
               ROUND(AVG(total) OVER (ORDER BY jour ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2),
               ROW_NUMBER() OVER (ORDER BY jour)
        FROM jours
        ORDER BY jour
    """)

    return [
        {
            "jour": r[0].isoformat(),
            "total": r[1],
            "traitees": r[2],
            "moyenne_mobile_7j": _number(r[3]),
            "partiel": r[4] < 7,
        }
        for r in rows
    ]


@router.get("/stats/ops/isp-technology-matrix")
def get_isp_technology_matrix(db: Session = Depends(get_db)):
    """Resolution rate crossed by provider x technology.

    Returned flat (one row per cell): the front-end does the pivoting. A matrix
    pre-pivoted in JSON would force the API to be republished as soon as an ISP
    enters or leaves the referential.
    """
    rows = _rows(db, """
        SELECT
            fsi,
            split_part(ref_demande, '/', 1)                       AS technologie,
            COUNT(*)                                              AS total,
            COUNT(*) FILTER (WHERE etat_ot = 'Traite')            AS traitees,
            ROUND(COUNT(*) FILTER (WHERE etat_ot = 'Traite') * 100.0
                  / NULLIF(COUNT(*), 0), 1)                       AS taux_resolution
        FROM reclamations_workflow
        WHERE fsi IS NOT NULL
          AND split_part(ref_demande, '/', 1) IN ('ADSL', 'VDSL', 'GPON')
        GROUP BY fsi, split_part(ref_demande, '/', 1)
        ORDER BY fsi, technologie
    """)

    return [
        {
            "fsi": r[0],
            "technologie": r[1],
            "total": r[2],
            "traitees": r[3],
            "taux_resolution": _number(r[4]),
        }
        for r in rows
    ]


@router.get("/stats/ops/pareto-of-causes")
def get_pareto_of_causes(db: Session = Depends(get_db)):
    """Pareto diagram of the root causes of anomalies.

    The diagnosis is stored as free text by `comparator.py`. The
    classification follows the order of its own rules: an anomaly whose cause is
    a high attenuation is counted as such and not as "insufficient rate", which
    is only its observed symptom. The order of the `WHEN` clauses therefore
    carries the business meaning — moving one would change the breakdown.

    Each branch matches both the current English wording and the legacy French
    wording, so journal rows written before the platform was translated keep
    their correct classification instead of collapsing into "Other".
    """
    rows = _rows(db, """
        WITH classees AS (
            SELECT CASE
                WHEN message_log LIKE 'Physical anomaly%'
                  OR message_log LIKE 'Anomalie physique%'              THEN 'Physical anomaly (AI model)'
                WHEN message_log LIKE '%down (Idle)%'
                  OR message_log LIKE '%coupure (Idle)%'                THEN 'Line down'
                WHEN message_log LIKE '%High line attenuation%'
                  OR message_log LIKE '%Atténuation de ligne élevée%'   THEN 'High attenuation'
                WHEN message_log LIKE '%Low signal-to-noise margin%'
                  OR message_log LIKE '%Marge de bruit (SNR) faible%'   THEN 'Low SNR margin'
                WHEN message_log LIKE '%Maximum attainable rate%'
                  OR message_log LIKE '%Débit maximum atteignable%'     THEN 'Under-dimensioned infrastructure'
                WHEN message_log LIKE 'Insufficient rate%'
                  OR message_log LIKE 'Débit insuffisant%'              THEN 'Insufficient rate (undetermined cause)'
                ELSE 'Other'
            END AS cause
            FROM logs_followup
            WHERE statut_test = 'ANOMALIE'
        )
        SELECT cause,
               COUNT(*)                                                     AS nb,
               ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1)           AS part,
               ROUND(SUM(COUNT(*)) OVER (ORDER BY COUNT(*) DESC, cause
                                         ROWS UNBOUNDED PRECEDING)
                     * 100.0 / SUM(COUNT(*)) OVER (), 1)                    AS cumul
        FROM classees
        GROUP BY cause
        ORDER BY nb DESC, cause
    """)

    return [
        {
            "cause": r[0],
            "nb": r[1],
            "part": _number(r[2]),
            "cumul": _number(r[3]),
        }
        for r in rows
    ]


# ══════════════════════════════════════════════════
# 3. DATA QUALITY
# ══════════════════════════════════════════════════

# Columns monitored for completeness, per table. Restricted to the columns that
# carry a business decision: a fill rate on a primary key would always be 100%
# and would drown out the real gaps.
MONITORED_COLUMNS = {
    "mesures_netscan": [
        "channel_rate_kbps", "status_training", "line_snr_margin_down",
        "line_attenuation_down", "max_attainable_rate_kbps", "distance_approx_km",
        "total_output_power_dbm", "signal_attenuation_down", "line_snr_margin_up",
    ],
    "reclamations_workflow": [
        "num_appel", "etat_ot", "date_etat", "debit", "fsi", "zone",
        "id_technicien", "type_ot", "position_site_nouvelle", "position_rla",
    ],
}


@router.get("/stats/data-quality")
def get_data_quality(db: Session = Depends(get_db)):
    """Observability of the data estate: volumetry, freshness, completeness,
    referential integrity and referential coherence.

    This page does not judge the quality of the NETWORK but that of the DATA
    used to judge it. An indicator computed on a column that is 100% empty is a
    false indicator — better to know before publishing it.
    """
    volumetrie = _rows(db, """
        SELECT 'clients', COUNT(*), pg_size_pretty(pg_total_relation_size('clients')) FROM clients
        UNION ALL SELECT 'techniciens', COUNT(*), pg_size_pretty(pg_total_relation_size('techniciens')) FROM techniciens
        UNION ALL SELECT 'reclamations_workflow', COUNT(*), pg_size_pretty(pg_total_relation_size('reclamations_workflow')) FROM reclamations_workflow
        UNION ALL SELECT 'mesures_netscan', COUNT(*), pg_size_pretty(pg_total_relation_size('mesures_netscan')) FROM mesures_netscan
        UNION ALL SELECT 'logs_followup', COUNT(*), pg_size_pretty(pg_total_relation_size('logs_followup')) FROM logs_followup
    """)

    fraicheur = _rows(db, """
        SELECT
            (SELECT MAX(timestamp_mesure) FROM mesures_netscan),
            (SELECT MAX(date_test)        FROM logs_followup),
            (SELECT MAX(date_etat)        FROM reclamations_workflow),
            NOW()::timestamp
    """)[0]

    # Completeness: one query per table, every column in a single pass.
    completude = []
    for table, columns in MONITORED_COLUMNS.items():
        selections = ", ".join(f'COUNT("{c}")' for c in columns)
        values_row = _rows(db, f"SELECT COUNT(*), {selections} FROM {table}")[0]
        total = values_row[0]
        for index, column in enumerate(columns, start=1):
            rempli = values_row[index]
            completude.append({
                "table": table,
                "colonne": column,
                "total": total,
                "renseigne": rempli,
                "taux": round(rempli * 100.0 / total, 1) if total else 0.0,
            })

    integrite = _rows(db, """
        SELECT
            (SELECT COUNT(*) FROM reclamations_workflow r
              LEFT JOIN clients c ON c.num_telephone = r.num_appel
              WHERE c.num_telephone IS NULL),
            (SELECT COUNT(*) FROM mesures_netscan m
              LEFT JOIN clients c ON c.num_telephone = m.num_appel
              WHERE c.num_telephone IS NULL),
            (SELECT COUNT(*) FROM logs_followup l
              LEFT JOIN reclamations_workflow r ON r.ref_demande = l.ref_demande
              WHERE r.ref_demande IS NULL),
            (SELECT COUNT(*) FROM reclamations_workflow WHERE id_technicien IS NULL),
            (SELECT COUNT(*) FROM reclamations_workflow r
              WHERE r.id_technicien IS NULL AND r.etat_ot <> 'Emis'),
            (SELECT COUNT(*) FROM clients c
              LEFT JOIN mesures_netscan m ON m.num_appel = c.num_telephone
              WHERE m.id_mesure IS NULL),
            (SELECT COUNT(*) FROM techniciens t
              LEFT JOIN reclamations_workflow r ON r.id_technicien = t.id_technicien
              WHERE r.ref_demande IS NULL),
            (SELECT COUNT(*) FROM (
                SELECT num_appel, timestamp_mesure FROM mesures_netscan
                GROUP BY 1, 2 HAVING COUNT(*) > 1) d)
    """)[0]

    coherence = _rows(db, """
        SELECT status_training, COUNT(*)
        FROM mesures_netscan
        GROUP BY status_training
        ORDER BY COUNT(*) DESC
    """)

    cadence = _rows(db, """
        SELECT timestamp_mesure::date            AS jour,
               COUNT(*)                          AS nb_mesures,
               COUNT(DISTINCT num_appel)         AS nb_lignes,
               COUNT(line_snr_margin_down)       AS nb_snr
        FROM mesures_netscan
        GROUP BY 1
        ORDER BY 1
    """)

    aberrations = _rows(db, """
        SELECT
            (SELECT COUNT(*) FROM mesures_netscan WHERE channel_rate_kbps = 0),
            (SELECT COUNT(*) FROM mesures_netscan WHERE channel_rate_kbps < 0),
            (SELECT COUNT(*) FROM mesures_netscan WHERE line_snr_margin_down < 0),
            (SELECT COUNT(*) FROM mesures_netscan WHERE timestamp_mesure > NOW()),
            (SELECT COUNT(*) FROM reclamations_workflow WHERE date_etat > NOW())
    """)[0]

    maintenant = fraicheur[3]

    def _age_heures(horodatage) -> float | None:
        if horodatage is None:
            return None
        return round((maintenant - horodatage).total_seconds() / 3600, 1)

    return {
        "volumetrie": [
            {"table": r[0], "lignes": r[1], "taille": r[2]} for r in volumetrie
        ],
        "fraicheur": [
            {
                "flux": "NetScan measurements",
                "table": "mesures_netscan",
                "dernier": fraicheur[0].isoformat() if fraicheur[0] else None,
                "age_heures": _age_heures(fraicheur[0]),
            },
            {
                "flux": "Compliance controls",
                "table": "logs_followup",
                "dernier": fraicheur[1].isoformat() if fraicheur[1] else None,
                "age_heures": _age_heures(fraicheur[1]),
            },
            {
                "flux": "Work-order status changes",
                "table": "reclamations_workflow",
                "dernier": fraicheur[2].isoformat() if fraicheur[2] else None,
                "age_heures": _age_heures(fraicheur[2]),
            },
        ],
        "completude": completude,
        "integrite": [
            {"controle": "Work orders with no customer in the referential",
             "anomalies": integrite[0], "bloquant": True},
            {"controle": "Measurements with no customer in the referential",
             "anomalies": integrite[1], "bloquant": True},
            {"controle": "Logs attached to a non-existent work order",
             "anomalies": integrite[2], "bloquant": True},
            {"controle": "Duplicates (same line, same timestamp)",
             "anomalies": integrite[7], "bloquant": True},
            # An "Emis" (issued) work order is not assigned yet: the absence of a
            # technician is normal there. Only engaged work orders without a
            # technician are a defect.
            {"controle": "Engaged work orders with no technician assigned",
             "anomalies": integrite[4], "bloquant": True},
            {"controle": "Work orders with no technician (including \"Issued\", expected)",
             "anomalies": integrite[3], "bloquant": False},
            {"controle": "Customers with no NetScan measurement at all",
             "anomalies": integrite[5], "bloquant": False},
            {"controle": "Technicians with no intervention at all",
             "anomalies": integrite[6], "bloquant": False},
        ],
        "coherence": [
            {"valeur": r[0] or "(not populated)", "nb": r[1]} for r in coherence
        ],
        "cadence": [
            {
                "jour": r[0].isoformat(),
                "nb_mesures": r[1],
                "nb_lignes": r[2],
                "nb_snr": r[3],
            }
            for r in cadence
        ],
        "aberrations": [
            {"controle": "Measured rate is zero (line down)", "anomalies": aberrations[0]},
            {"controle": "Negative measured rate", "anomalies": aberrations[1]},
            {"controle": "Negative SNR margin", "anomalies": aberrations[2]},
            {"controle": "Measurement timestamped in the future", "anomalies": aberrations[3]},
            {"controle": "Status change in the future", "anomalies": aberrations[4]},
        ],
    }
