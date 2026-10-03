"""
main.py — FastAPI backend (NetVerify)
Project: NetVerify — Tunisie Telecom

Adapted to the real ORM schema defined in database.py:
- Client, Technician, WorkOrder, NetscanMeasurement, LogFollowup

Run with: python -m uvicorn main:app --reload
Interactive documentation: http://127.0.0.1:8000/docs
"""

# ══════════════════════════════════════════════════
# 1. IMPORTS — ALWAYS FIRST
# ══════════════════════════════════════════════════
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, text
from typing import Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Before every local import: database.py, security.py and chatbot_ai.py read
# their configuration when they are imported, so the `.env` has to be in
# os.environ by then.
from env_file import load_env_files

load_env_files()

from database import (
    SessionLocal, engine, AuditEntry, Client, Technician,
    WorkOrder, NetscanMeasurement, LogFollowup, User
)
import analytics
import security
from comparator import check_compliance, VERIFICATION_DELAY_DAYS
from netscan_simulator import run_single_measurement
from chatbot_ai import generate_answer as generate_ai_answer, PROVIDER_ERRORS


# The main function of the comparator.py script
from comparator import check_compliance


# ══════════════════════════════════════════════════
# 2. FASTAPI APPLICATION CREATION
# ══════════════════════════════════════════════════
app = FastAPI(
    title="NetVerify API — Tunisie Telecom",
    description="Post-intervention follow-up and quality-of-service verification system",
    version="1.0.0"
)


# ══════════════════════════════════════════════════
# 2b. RATE LIMITING
#    The platform is internal, but it is reachable: without a ceiling a single
#    client can exhaust the database, and above all the assistant —
#    /chatbot/query runs an inference per call, which monopolises the GPU
#    locally and is billed per call on Gemini. The global ceiling covers
#    everything; the sensitive endpoints carry their own, stricter one.
# ══════════════════════════════════════════════════
limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Authorisation shortcuts, so that each route declares readably what it
# requires. A platform reserved for technicians has no anonymous read route:
# the only exception is "/", the availability probe that the dashboard calls
# even before the sign-in screen.
#
# `SUPERVISION` guards what compares the field agents with one another — the
# nominative rankings and the audit trail. A technician is not blinded, they
# read their own figures on /stats/my-performance; what they do not read is
# their colleagues' names next to a score. Same reasoning as BULK_OPERATION,
# which guards the run that *produces* those scores.
AUTH = Depends(security.current_user)
SUPERVISION = Depends(security.require_role(*security.SUPERVISION_ROLES))
BULK_OPERATION = Depends(security.automaton_or_supervisor)

# The journal of the privileged actions is created on start-up if it is missing:
# an audit trail must not depend on somebody having remembered to run a
# migration. `checkfirst` makes the call a no-op on every later boot.
AuditEntry.__table__.create(engine, checkfirst=True)


# ══════════════════════════════════════════════════
# 3. CORS MIDDLEWARE — allows the front-ends (React on 5173, Streamlit
#    dashboard on 8501, and the chatbot widget embedded in a sandboxed iframe
#    whose origin is "null"). MUST come AFTER the creation of "app".
#    No cookies/auth here, so allow_credentials=False + origin "*" is safe and
#    also covers the iframe's "null" origin.
# ══════════════════════════════════════════════════
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════
# 4b. ADVANCED ANALYTICAL ENDPOINTS
#    Distributions, percentiles, correlations, Pareto and data-quality controls
#    live in analytics.py: they are statistical analyses, not CRUD, and their
#    SQL is too bulky to stay here.
# ══════════════════════════════════════════════════
app.include_router(analytics.router, dependencies=[AUTH])


# ══════════════════════════════════════════════════
# 4. DATABASE DEPENDENCY
# ══════════════════════════════════════════════════
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ══════════════════════════════════════════════════
# 5. PYDANTIC SCHEMAS (for responses / inputs)
# ══════════════════════════════════════════════════
class ManualMeasurement(BaseModel):
    num_telephone: str


class SignInRequest(BaseModel):
    login: str
    password: str


# ══════════════════════════════════════════════════
# 5b. AUTHENTICATION
#    Placed after `get_db`: `Depends(get_db)` is a default value, therefore
#    evaluated at the moment Python defines the function. Declaring these
#    routes higher up would raise a NameError as soon as the module is imported.
# ══════════════════════════════════════════════════
@app.post("/auth/login")
@limiter.limit("5/minute")
def sign_in(
    request: Request,
    request_body: SignInRequest,
    db: Session = Depends(get_db),
):
    """Exchanges a login and a password for a session token.

    Capped at 5 attempts per minute and per address: a dictionary attack
    becomes unusable without getting in the way of a technician who mistypes a
    key.

    The failure message never distinguishes "unknown account" from "wrong
    password". Distinguishing them would allow valid logins to be enumerated.
    """
    # `identifiant` is the column of the `utilisateurs` table, kept as the
    # database spells it; the request and the response speak English.
    user = db.query(User).filter_by(identifiant=request_body.login).first()

    # The verification is performed even when the account does not exist,
    # against a decoy hash: without it, an instant reply would betray the
    # non-existence of the account where a real account costs ~250 ms of bcrypt.
    digest = user.mot_de_passe_hash if user else security.DECOY_HASH
    password_ok = security.verify_password(request_body.password, digest)

    if user is None or not password_ok:
        raise HTTPException(status_code=401, detail="Incorrect login or password.")
    if not user.actif:
        raise HTTPException(
            status_code=403,
            detail="Account deactivated. Contact the NetVerify administrator.",
        )

    token, duration = security.create_token(
        user.identifiant, security.normalise_role(user.role)
    )
    user.derniere_connexion = datetime.utcnow()
    db.commit()

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": duration,
        "login": user.identifiant,
        "full_name": user.nom_complet,
        "role": security.normalise_role(user.role),
    }


@app.get("/auth/me")
def current_profile(user: User = AUTH):
    """Profile of the token holder — used by the dashboard to validate a session."""
    return {
        "login": user.identifiant,
        "full_name": user.nom_complet,
        "role": security.normalise_role(user.role),
        "technician_id": user.id_technicien,
        "last_sign_in": user.derniere_connexion,
    }


# ══════════════════════════════════════════════════
# ROOT ROUTE
# ══════════════════════════════════════════════════
@app.get("/")
def root():
    return {
        "message": "NetVerify API — Tunisie Telecom",
        "version": "1.0.0",
        "status": "running"
    }


# ══════════════════════════════════════════════════
# ENDPOINTS — CUSTOMERS
# ══════════════════════════════════════════════════
@app.get("/clients", dependencies=[AUTH])
def get_clients(
    technology: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Lists the customers, with an optional filter by technology (ADSL/VDSL/GPON)"""
    query = db.query(Client)
    if technology:
        query = query.filter(Client.techno_souscrite == technology)
    return query.limit(limit).all()


@app.get("/clients/{num_telephone}", dependencies=[AUTH])
def get_client(num_telephone: str, db: Session = Depends(get_db)):
    """Details of a customer + their work orders and latest measurement"""
    client = db.query(Client).filter(Client.num_telephone == num_telephone).first()
    if not client:
        raise HTTPException(status_code=404, detail="Customer not found")

    latest_measurement = db.query(NetscanMeasurement)\
        .filter_by(num_appel=num_telephone)\
        .order_by(desc(NetscanMeasurement.timestamp_mesure))\
        .first()

    return {
        "num_telephone": client.num_telephone,
        "nom_client": client.nom_client,
        "techno_souscrite": client.techno_souscrite,
        "nb_reclamations": len(client.work_orders),
        "derniere_mesure": latest_measurement
    }


# ══════════════════════════════════════════════════
# ENDPOINTS — WORK ORDERS (ReclamationWorkflow)
# ══════════════════════════════════════════════════
@app.get("/work-orders", dependencies=[AUTH])
def get_work_orders(
    etat_ot: Optional[str] = None,
    fsi: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Lists the work orders with optional filters"""
    query = db.query(WorkOrder)
    if etat_ot:
        query = query.filter(WorkOrder.etat_ot == etat_ot)
    if fsi:
        query = query.filter(WorkOrder.fsi == fsi)
    return query.order_by(desc(WorkOrder.date_etat)).limit(limit).all()


@app.get("/work-orders/{ref_demande}", dependencies=[AUTH])
def get_work_order(ref_demande: str, db: Session = Depends(get_db)):
    """Details of a work order, with its latest measurement and its logs"""
    rec = db.query(WorkOrder).filter_by(ref_demande=ref_demande).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Work order not found")

    latest_measurement = db.query(NetscanMeasurement)\
        .filter_by(num_appel=rec.num_appel)\
        .order_by(desc(NetscanMeasurement.timestamp_mesure))\
        .first()

    return {
        "work_order": rec,
        "derniere_mesure": latest_measurement,
        "logs": rec.followup_logs
    }


@app.get("/work-orders-to-verify", dependencies=[AUTH])
def get_work_orders_to_verify(db: Session = Depends(get_db)):
    """
    Work orders in the 'Traite' (processed) state for at least 14 days
    (therefore eligible for the compliance verification)
    """
    date_limite = datetime.utcnow() - timedelta(days=VERIFICATION_DELAY_DAYS)

    result = db.query(WorkOrder).filter(
        WorkOrder.etat_ot == "Traite",
        WorkOrder.date_etat <= date_limite
    ).order_by(WorkOrder.date_etat).all()

    return {"count": len(result), "reclamations": result}


# ══════════════════════════════════════════════════
# ENDPOINTS — NETSCAN MEASUREMENTS
# ══════════════════════════════════════════════════
@app.get("/measurements/{num_appel}", dependencies=[AUTH])
def get_customer_measurements(num_appel: str, limit: int = 10, db: Session = Depends(get_db)):
    """History of the NetScan measurements of a customer"""
    measurements = db.query(NetscanMeasurement)\
        .filter_by(num_appel=num_appel)\
        .order_by(desc(NetscanMeasurement.timestamp_mesure))\
        .limit(limit).all()

    if not measurements:
        raise HTTPException(status_code=404, detail="No measurement found for this customer")
    return measurements


@app.post("/measurements/refresh", dependencies=[AUTH])
def refresh_measurement(data: ManualMeasurement, db: Session = Depends(get_db)):
    """Manually triggers a new NetScan measurement for a given customer"""
    try:
        run_single_measurement(data.num_telephone, db)
        db.commit()
        return {"message": f"Measurement refreshed for {data.num_telephone}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════
# ENDPOINTS — ANOMALY LOGS (LogFollowup)
# ══════════════════════════════════════════════════
@app.get("/logs", dependencies=[AUTH])
def get_logs(
    statut_test: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Lists the detected anomaly logs"""
    query = db.query(LogFollowup)
    if statut_test:
        query = query.filter(LogFollowup.statut_test == statut_test)
    return query.order_by(desc(LogFollowup.date_test)).limit(limit).all()


# ══════════════════════════════════════════════════
# ENDPOINT — AUDIT TRAIL OF THE PRIVILEGED ACTIONS
#    `logs_followup` says what the control found; `journal_actions` says who
#    asked for it. Reserved for supervisors: it names the people who acted, and
#    is therefore nominative in the same sense as the rankings above.
# ══════════════════════════════════════════════════
@app.get("/audit", dependencies=[SUPERVISION])
def get_audit_trail(
    resultat: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Last privileged actions: bulk runs, and the attempts that were refused."""
    query = db.query(AuditEntry)
    if resultat:
        query = query.filter(AuditEntry.resultat == resultat)

    entries = query.order_by(desc(AuditEntry.horodatage))\
                   .limit(max(1, min(limit, 500))).all()

    return [{"id_action": e.id_action, "horodatage": e.horodatage,
             "auteur": e.auteur, "role": e.role, "action": e.action,
             "resultat": e.resultat, "details": e.details}
            for e in entries]


# ══════════════════════════════════════════════════
# ENDPOINT — MANUAL TRIGGER OF THE VERIFICATION
# ══════════════════════════════════════════════════
@app.post("/verification/run")
@limiter.limit("6/hour")
def run_manual_verification(
    request: Request, caller: security.Caller = BULK_OPERATION
):
    """
    Manually triggers the D+14 compliance verification
    (equivalent to running `python comparator.py`)

    Restricted to supervisors: the run walks the whole estate and writes to the
    anomaly journal — and it writes the very figures on which the field agents
    are judged, which is why the agents themselves cannot launch it. Capped at 6
    executions per hour — beyond that it is a loop, not a business need.

    The trigger is journalled either way. A run that failed halfway is the one
    an audit most needs to find, so the failure is recorded before the 500 is
    raised.
    """
    try:
        result = check_compliance()
    except Exception as e:
        security.record_action(caller.name, request.url.path,
                               security.OUTCOME_FAILURE, details=str(e)[:500],
                               role=caller.role)
        raise HTTPException(status_code=500, detail=str(e))

    security.record_action(
        caller.name, request.url.path, security.OUTCOME_SUCCESS,
        details=f"{result['nb_anomalies']} anomaly(ies), "
                f"{result['nb_conformes']} compliant, "
                f"{result['nb_sans_mesure']} without a measurement",
        role=caller.role,
    )
    # The counts were computed and thrown away: returning them lets the
    # interface report the same summary whether the run went through n8n or
    # straight to the backend.
    return {
        "message": "Verification completed successfully",
        "nb_conformes": result["nb_conformes"],
        "nb_anomalies": result["nb_anomalies"],
        "nb_sans_mesure": result["nb_sans_mesure"],
    }


# ══════════════════════════════════════════════════
# ENDPOINTS — STATISTICS (for the dashboard)
# ══════════════════════════════════════════════════
@app.get("/stats/kpis", dependencies=[AUTH])
def get_kpis(db: Session = Depends(get_db)):
    """Main KPIs"""
    total_work_order_count = db.query(func.count(WorkOrder.ref_demande)).scalar()
    total_processed_count = db.query(func.count(WorkOrder.ref_demande))\
        .filter(WorkOrder.etat_ot == "Traite").scalar()
    total_anomaly_count = db.query(func.count(LogFollowup.id_log))\
        .filter(LogFollowup.statut_test == "ANOMALIE").scalar()
    total_customer_count = db.query(func.count(Client.num_telephone)).scalar()

    date_limite = datetime.utcnow() - timedelta(days=VERIFICATION_DELAY_DAYS)
    to_verify = db.query(func.count(WorkOrder.ref_demande)).filter(
        WorkOrder.etat_ot == "Traite",
        WorkOrder.date_etat <= date_limite
    ).scalar()

    return {
        "total_reclamations": total_work_order_count,
        "total_traitees": total_processed_count,
        "total_anomalies": total_anomaly_count,
        "total_clients": total_customer_count,
        "reclamations_a_verifier": to_verify
    }


@app.get("/stats/by-technology", dependencies=[AUTH])
def get_stats_by_technology(db: Session = Depends(get_db)):
    """Statistics per technology (ADSL/VDSL/GPON)"""
    result = db.query(
        Client.techno_souscrite,
        func.count(Client.num_telephone).label("nb_clients")
    ).group_by(Client.techno_souscrite).all()

    return [{"technology": r[0], "nb_clients": r[1]} for r in result]


@app.get("/stats/by-isp", dependencies=[AUTH])
def get_stats_by_isp(db: Session = Depends(get_db)):
    """Statistics per ISP"""
    result = db.query(
        WorkOrder.fsi,
        func.count(WorkOrder.ref_demande).label("nb_reclamations")
    ).group_by(WorkOrder.fsi).all()

    return [{"fsi": r[0], "nb_reclamations": r[1]} for r in result]


@app.get("/stats/by-status", dependencies=[AUTH])
def get_stats_by_status(db: Session = Depends(get_db)):
    """Breakdown of the work orders by status (Emis / En cours / Traite)"""
    result = db.query(
        WorkOrder.etat_ot,
        func.count(WorkOrder.ref_demande).label("nb")
    ).group_by(WorkOrder.etat_ot).all()

    return [{"etat_ot": r[0], "nb": r[1]} for r in result]


@app.get("/stats/anomalies-by-technician", dependencies=[SUPERVISION])
def get_anomalies_by_technician(db: Session = Depends(get_db)):
    """Number of anomalies detected per technician — supervisors only.

    Nominative: it names the field agents and ranks them. A technician reads
    their own count on `/stats/my-performance` instead.
    """
    result = db.query(
        WorkOrder.id_technicien,
        func.count(LogFollowup.id_log).label("nb_anomalies")
    ).join(LogFollowup, LogFollowup.ref_demande == WorkOrder.ref_demande)\
     .group_by(WorkOrder.id_technicien)\
     .order_by(desc("nb_anomalies"))\
     .limit(10).all()

    return [{"id_technicien": r[0], "nb_anomalies": r[1]} for r in result]
@app.get("/stats/anomalies-by-technology", dependencies=[AUTH])
def get_anomalies_by_technology(db: Session = Depends(get_db)):
    """Number of anomalies detected per technology"""
    result = db.execute(text("""
    SELECT
        split_part(ref_demande, '/', 1) AS technologie,
        COUNT(*) AS total_reclamations
    FROM reclamations_workflow
    WHERE ref_demande LIKE 'GPON%'
       OR ref_demande LIKE 'ADSL%'
       OR ref_demande LIKE 'VDSL%'
    GROUP BY split_part(ref_demande, '/', 1)
    ORDER BY total_reclamations DESC
    """)).fetchall()
    return [{"technologie": r[0], "nb_anomalies": r[1]} for r in result]
# ══════════════════════════════════════════════════
# NEW ENDPOINTS FOR THE ADVANCED DASHBOARDS
# To be added in main.py before the "if __name__"
# ══════════════════════════════════════════════════

@app.get("/stats/monthly-trend", dependencies=[AUTH])
def get_monthly_trend(db: Session = Depends(get_db)):
    """Evolution of the number of work orders per month"""
    result = db.execute(text("""
        SELECT
            TO_CHAR(date_etat, 'YYYY-MM') AS mois,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE etat_ot = 'Traite') AS traitees,
            COUNT(*) FILTER (WHERE etat_ot = 'En cours') AS en_cours,
            COUNT(*) FILTER (WHERE etat_ot = 'Emis') AS emises
        FROM reclamations_workflow
        WHERE date_etat IS NOT NULL
        GROUP BY TO_CHAR(date_etat, 'YYYY-MM')
        ORDER BY mois ASC
    """)).fetchall()
    return [{"mois": r[0], "total": r[1], "traitees": r[2],
             "en_cours": r[3], "emises": r[4]} for r in result]


@app.get("/stats/rate-comparison", dependencies=[AUTH])
def get_debit_comparison(db: Session = Depends(get_db)):
    """Comparison of the promised rate vs the measured rate, per technology"""
    result = db.execute(text("""
        SELECT
            split_part(r.ref_demande, '/', 1) AS technologie,
            AVG(CAST(regexp_replace(r.debit, '[^0-9]', '', 'g') AS FLOAT) * 1024) AS debit_promis_kbps,
            AVG(m.channel_rate_kbps) AS debit_mesure_kbps,
            COUNT(*) AS nb_clients
        FROM reclamations_workflow r
        JOIN mesures_netscan m ON m.num_appel = r.num_appel
        WHERE m.channel_rate_kbps IS NOT NULL
        AND (r.ref_demande LIKE 'ADSL%'
          OR r.ref_demande LIKE 'VDSL%'
          OR r.ref_demande LIKE 'GPON%')
        GROUP BY split_part(r.ref_demande, '/', 1)
        ORDER BY technologie
    """)).fetchall()
    return [{"technologie": r[0],
             "debit_promis_kbps": round(r[1], 0) if r[1] else 0,
             "debit_mesure_kbps": round(r[2], 0) if r[2] else 0,
             "nb_clients": r[3]} for r in result]


@app.get("/stats/compliance-by-technician", dependencies=[SUPERVISION])
def get_compliance_by_technician(db: Session = Depends(get_db)):
    """Compliance rate per technician — supervisors only.

    This is the evaluation of the field agents: it belongs to whoever is
    responsible for them, not to their peers. See `/stats/my-performance` for
    the self-view offered to a technician.
    """
    result = db.execute(text("""
        SELECT
            r.id_technicien,
            COUNT(*) AS total_interventions,
            COUNT(*) FILTER (WHERE r.etat_ot = 'Traite') AS traitees,
            ROUND(
                COUNT(*) FILTER (WHERE r.etat_ot = 'Traite') * 100.0
                / NULLIF(COUNT(*), 0), 1
            ) AS taux_conformite
        FROM reclamations_workflow r
        WHERE r.id_technicien IS NOT NULL
        GROUP BY r.id_technicien
        ORDER BY taux_conformite DESC
        LIMIT 15
    """)).fetchall()
    return [{"id_technicien": r[0], "total": r[1],
             "traitees": r[2], "taux_conformite": float(r[3]) if r[3] else 0}
            for r in result]


# ══════════════════════════════════════════════════
# ENDPOINTS — SELF-VIEW OF A TECHNICIAN
#    The counterpart of the two nominative endpoints above. Closing the
#    comparative ranking to the field agents would leave them without any
#    feedback at all, which is not the intent: they read their own figures, and
#    the team is present only as an anonymous benchmark (median, headcount, how
#    many peers score below them). No colleague is ever named.
#
#    The perimeter comes from `utilisateurs.id_technicien`, read from the token
#    holder and never from a query parameter: passing the identifier in the URL
#    would let anyone read anyone by changing a character.
# ══════════════════════════════════════════════════
@app.get("/stats/my-performance")
def get_my_performance(user: User = AUTH, db: Session = Depends(get_db)):
    """Own results of the token holder, against an anonymous team benchmark."""
    id_technicien = user.id_technicien

    # A supervisor, or an account not attached to an operational record, has no
    # interventions of their own. Answered with a 200 and `linked: false` rather
    # than a 404: it is a legitimate state of the account, not a failed call,
    # and the interface explains it instead of showing an error.
    if not id_technicien:
        return {
            "linked": False,
            "role": security.normalise_role(user.role),
            "technician_id": None,
            "technician_name": None,
        }

    technician = db.query(Technician).filter_by(id_technicien=id_technicien).first()

    # One query: my aggregate, the team median and my position, all derived from
    # the same CTE so the benchmark can never be computed on a different
    # perimeter than the figure it is compared with.
    compliance = db.execute(text("""
        WITH par_technicien AS (
            SELECT id_technicien,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE etat_ot = 'Traite') AS traitees,
                   COUNT(*) FILTER (WHERE etat_ot = 'Traite') * 100.0
                       / NULLIF(COUNT(*), 0) AS taux
            FROM reclamations_workflow
            WHERE id_technicien IS NOT NULL
            GROUP BY id_technicien
        ),
        moi AS (SELECT * FROM par_technicien WHERE id_technicien = :tech)
        SELECT
            (SELECT total FROM moi)                                   AS total,
            (SELECT traitees FROM moi)                                AS traitees,
            (SELECT ROUND(taux::numeric, 1) FROM moi)                 AS taux,
            (SELECT COUNT(*) FROM par_technicien)                     AS effectif,
            (SELECT ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY taux)::numeric, 1)
               FROM par_technicien)                                   AS mediane,
            (SELECT COUNT(*) FROM par_technicien p, moi m WHERE p.taux < m.taux)
                                                                      AS moins_bons
    """), {"tech": id_technicien}).fetchone()

    anomalies = db.execute(text("""
        WITH par_technicien AS (
            SELECT r.id_technicien,
                   COUNT(*) FILTER (WHERE l.statut_test = 'ANOMALIE') AS nb
            FROM reclamations_workflow r
            JOIN logs_followup l ON l.ref_demande = r.ref_demande
            WHERE r.id_technicien IS NOT NULL
            GROUP BY r.id_technicien
        )
        SELECT
            COALESCE((SELECT nb FROM par_technicien WHERE id_technicien = :tech), 0) AS nb,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY nb)::numeric, 1)       AS mediane
        FROM par_technicien
    """), {"tech": id_technicien}).fetchone()

    total = compliance[0] or 0

    return {
        "linked": True,
        "role": security.normalise_role(user.role),
        "technician_id": id_technicien,
        "technician_name": technician.nom_technicien if technician else None,
        # An account attached to a record that carries no intervention yet: the
        # benchmark is still returned, the personal figures are simply zero.
        "has_activity": bool(total),
        "total": int(total),
        "closed": int(compliance[1] or 0),
        "compliance_rate": float(compliance[2] or 0),
        "anomalies": int(anomalies[0] or 0) if anomalies else 0,
        "team_size": int(compliance[3] or 0),
        "team_median_compliance": float(compliance[4] or 0),
        "team_median_anomalies": float(anomalies[1] or 0) if anomalies else 0.0,
        "peers_below": int(compliance[5] or 0),
    }


@app.get("/stats/my-anomalies")
def get_my_anomalies(limit: int = 20, user: User = AUTH, db: Session = Depends(get_db)):
    """Gaps journalled on the token holder's own interventions.

    What makes the self-view actionable: not a score, but the list of the work
    orders to go back to, with the diagnosis produced by the comparator.
    """
    if not user.id_technicien:
        return []

    result = db.execute(text("""
        SELECT l.id_log, l.ref_demande, l.date_test, l.statut_test, l.message_log,
               r.num_appel
        FROM logs_followup l
        JOIN reclamations_workflow r ON r.ref_demande = l.ref_demande
        WHERE r.id_technicien = :tech
        ORDER BY l.date_test DESC
        LIMIT :limite
    """), {"tech": user.id_technicien, "limite": max(1, min(limit, 200))}).fetchall()

    return [{"id_log": r[0], "ref_demande": r[1], "date_test": r[2],
             "statut_test": r[3], "message_log": r[4], "num_appel": r[5]}
            for r in result]


@app.get("/stats/anomalies-by-zone", dependencies=[AUTH])
def get_anomalies_by_zone(db: Session = Depends(get_db)):
    """
    Anomalies per geographic zone — inferred from the intervention site.
    Grouped by prefix of position_site_nouvelle to simulate zones.

    The ILIKE patterns match the French wording stored in the column; only the
    returned labels are in English.
    """
    result = db.execute(text("""
        SELECT
            CASE
                WHEN position_site_nouvelle ILIKE '%Nord%' THEN 'North'
                WHEN position_site_nouvelle ILIKE '%Sud%'  THEN 'South'
                WHEN position_site_nouvelle ILIKE '%Est%'  THEN 'East'
                WHEN position_site_nouvelle ILIKE '%Ouest%' THEN 'West'
                WHEN position_site_nouvelle ILIKE '%Centre%' THEN 'Centre'
                ELSE 'Other'
            END AS zone,
            COUNT(*) AS total_reclamations,
            COUNT(*) FILTER (WHERE etat_ot = 'Traite') AS resolues
        FROM reclamations_workflow
        WHERE position_site_nouvelle IS NOT NULL
        GROUP BY zone
        ORDER BY total_reclamations DESC
    """)).fetchall()
    return [{"zone": r[0], "total": r[1], "resolues": r[2]} for r in result]
# ══════════════════════════════════════════════════
# MAP ENDPOINT — to be added in main.py
# ══════════════════════════════════════════════════

@app.get("/stats/work-orders-by-place", dependencies=[AUTH])
def get_work_orders_by_place(db: Session = Depends(get_db)):
    """Number of work orders per location (zone column of reclamations_workflow)"""
    result = db.execute(text("""
        SELECT
            zone,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE etat_ot = 'Traite')    AS traitees,
            COUNT(*) FILTER (WHERE etat_ot = 'En cours')  AS en_cours,
            COUNT(*) FILTER (WHERE etat_ot = 'Emis')      AS emises,
            split_part(ref_demande, '/', 1)               AS technologie_principale
        FROM reclamations_workflow
        WHERE zone IS NOT NULL
        GROUP BY zone, split_part(ref_demande, '/', 1)
        ORDER BY total DESC
    """)).fetchall()

    # GPS coordinates of the locations. The keys are the values stored in the
    # `zone` column, so the Tunisian place names are kept as they are.
    COORDS = {
        "Rue Jamel Abdennasser":             (36.7992, 10.1679),
        "Avenue de France":                  (36.7987, 10.1741),
        "Rue d'Angleterre":                  (36.7991, 10.1721),
        "Bab Bhar":                          (36.7982, 10.1764),
        "Médina de Tunis":                   (36.7987, 10.1703),
        "Le Passage":                        (36.7995, 10.1748),
        "Avenue de Madrid":                  (36.8001, 10.1734),
        "Avenue de Carthage":                (36.7978, 10.1756),
        "Lafayette":                         (36.8041, 10.1781),
        "Rue d'Algérie":                     (36.8005, 10.1712),
        "Place Barcelone":                   (36.7970, 10.1771),
        "Rue de Lyon":                       (36.8012, 10.1745),
        "Bab El Khadra":                     (36.8021, 10.1641),
        "Gare de Tunis-Marine (TGM)":        (36.8175, 10.2245),
        "Avenue de la République":           (36.8010, 10.1712),
        "Avenue du Ghana":                   (36.8050, 10.1720),
        "Bab Alioua":                        (36.7892, 10.1698),
        "Sidi El Béchir":                    (36.7921, 10.1745),
        "Sidi Mansour":                      (36.7845, 10.1612),
        "Gorgjani":                          (36.7901, 10.1698),
        "Bab Jedid":                         (36.7981, 10.1645),
        "Bab Menara":                        (36.7998, 10.1634),
        "Montfleury":                        (36.8081, 10.1841),
        "Dubosville":                        (36.8125, 10.1812),
        "El Ouardia":                        (36.7845, 10.1756),
        "Cité Ibn Sina":                     (36.7801, 10.1698),
        "Cité El Kabaria":                   (36.7756, 10.1712),
        "Zone Industrielle de Jebel Jelloud":(36.7678, 10.2012),
        "Jebel Jelloud":                     (36.7701, 10.1987),
        "Cité Mohamed Ali":                  (36.7834, 10.1823),
        "Sidi Fathallah":                    (36.7756, 10.1634),
        "Cité El Thawra":                    (36.7812, 10.1756),
        "Bir Kassaa":                        (36.7623, 10.1823),
    }

    data = []
    for r in result:
        zone = r[0]
        coords = COORDS.get(zone)
        if coords:
            data.append({
                "zone": zone,
                "total": r[1],
                "traitees": r[2],
                "en_cours": r[3],
                "emises": r[4],
                "technologie": r[5],
                "lat": coords[0],
                "lon": coords[1],
                "taux_resolution": round(r[2] / r[1] * 100, 1) if r[1] else 0
            })
    return data

@app.post("/measurements/refresh-all")
@limiter.limit("6/hour")
def refresh_all_measurements_endpoint(
    request: Request, caller: security.Caller = BULK_OPERATION
):
    """Refreshes the measurements of ALL customers — called by n8n

    Accepts either a supervisor JWT or the `X-Service-Token` header that n8n
    presents: the automaton has no password to type. Journalled in both cases,
    which is how the audit trail tells a 06:00 automatic run from a supervisor
    who forced one by hand.
    """
    db = SessionLocal()
    try:
        clients = db.query(Client).all()
        nb = 0
        for client in clients:
            # We pass the active db session down to avoid conflicts!
            run_single_measurement(client.num_telephone, db)
            nb += 1

        # 1. Move the return OUTSIDE the for loop (align it with 'for')
        # 2. Commit all 500 records at once here for blazing fast performance!
        db.commit()
        security.record_action(caller.name, request.url.path,
                               security.OUTCOME_SUCCESS,
                               details=f"{nb} measurement(s) refreshed",
                               role=caller.role)
        return {"message": f"{nb} measurements refreshed successfully"}

    except Exception as e:
        db.rollback() # Safely roll back changes if something goes wrong
        security.record_action(caller.name, request.url.path,
                               security.OUTCOME_FAILURE, details=str(e)[:500],
                               role=caller.role)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close() # Clean closure of the single session


@app.post("/measurements/verify-compliance")
@limiter.limit("6/hour")
def run_compliance_verification(
    request: Request, caller: security.Caller = BULK_OPERATION
):
    """Runs the D+14 analysis to detect the anomalies — called by n8n

    Same access rule as `/measurements/refresh-all`: supervisor, or automaton
    carrying the service token. Journalled the same way too.
    """
    try:
        # Direct call to the function of the comparator.py script
        result = check_compliance()
    except Exception as e:
        security.record_action(caller.name, request.url.path,
                               security.OUTCOME_FAILURE, details=str(e)[:500],
                               role=caller.role)
        raise HTTPException(status_code=500, detail=f"Error during the analysis: {str(e)}")

    security.record_action(
        caller.name, request.url.path, security.OUTCOME_SUCCESS,
        details=f"{result['nb_anomalies']} anomaly(ies), "
                f"{result['nb_conformes']} compliant, "
                f"{result['nb_sans_mesure']} without a measurement",
        role=caller.role,
    )
    return {
        "status": "success",
        "message": "D+14 compliance analysis completed successfully.",
        **result
    }


# ══════════════════════════════════════════════════
# ENDPOINT — AI CHATBOT (local model through Ollama; Gemini optional)
# ══════════════════════════════════════════════════
class ChatbotRequest(BaseModel):
    message: str


@app.post("/chatbot/query")
@limiter.limit("20/minute")
def chatbot_query(
    request: Request,
    request_body: ChatbotRequest,
    db: Session = Depends(get_db),
    user: User = AUTH,
):
    """NetVerify assistant — answers in natural language from the real database.

    This is the most expensive endpoint of the API: every call runs a language
    model inference, locally on the GPU by default, or against the Gemini quota
    when AI_PROVIDER=gemini. It is therefore both authenticated and capped at 20
    questions per minute. The body parameter is called `demande` and not
    `request`: slowapi
    requires the argument named `request` to be the HTTP request.

    The caller's role and technician record are passed down to the context
    builder. Without them the assistant would be a way round the whole role
    model: "how is TECH-042 doing?" would return that agent's name, phone number
    and anomaly count to anyone signed in, which is exactly what the nominative
    endpoints refuse to a technician.
    """
    try:
        return {"response": generate_ai_answer(
            request_body.message, db,
            role=security.normalise_role(user.role),
            id_technicien=user.id_technicien,
        )}
    except PROVIDER_ERRORS as e:
        # Quota exhausted, key refused, service unavailable: 502 designates the
        # third party. MUST precede `except RuntimeError`: AIProviderError
        # inherits from it, so the reverse order would make this branch
        # unreachable and turn every provider outage into an internal NetVerify
        # error.
        raise HTTPException(status_code=502, detail=f"AI provider error: {e}")
    except RuntimeError as e:
        # Missing configuration on the server side (absent API key): here
        # NetVerify really is at fault, not the provider.
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
