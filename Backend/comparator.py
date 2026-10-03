"""
comparator.py — Post-intervention verification module (NetVerify)
Project: NetVerify — Tunisie Telecom

Built on the real ORM schema defined in database.py:
- ReclamationWorkflow : holds the subscribed rate (column `debit`, free text)
- MesureNetscan       : holds the actually measured rate (`channel_rate_kbps`)
- LogFollowup         : records detected anomalies only

Logic:
1. Select the work orders in state "Traite" (processed) whose date_etat is at
   least 14 days old (D+14 delay)
2. Retrieve the latest NetScan measurement of the customer concerned
3. Compare the expected rate (text -> kbps, x1024) with the measured rate
4. On anomaly -> write a log_followup row with an enriched diagnosis
   (uses the NetScan technical data: SNR, attenuation, max attainable rate)
"""

from datetime import datetime, timedelta
from database import SessionLocal, WorkOrder, NetscanMeasurement, LogFollowup

# ══════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════
VERIFICATION_DELAY_DAYS = 14
TOLERANCE_THRESHOLD = 0.9   # 90% of the subscribed rate is deemed compliant (10% tolerance)
def parse_rate_kbps(rate_text: str) -> int:
    """
    Converts "10 mbps" -> 10240 kbps (x1024, consistent with netscan_simulator.py)
    """
    try:
        chiffre_debit = int(''.join(filter(str.isdigit, rate_text)))
        return chiffre_debit * 1024
    except (ValueError, TypeError):
        return 10240  # default value when the format is unreadable


def extract_line_type(ref_demande: str) -> str:
    """Extracts the line type from ref_demande (e.g. 'ADSL/2026/15004' -> 'ADSL')"""
    if not ref_demande:
        return "ADSL"
    return ref_demande.split("/")[0].strip().upper()


# ══════════════════════════════════════════════════
# 2. ENRICHED DIAGNOSIS (no LLM — business rules)
# ══════════════════════════════════════════════════
def determine_probable_cause(measurement: NetscanMeasurement, line_type: str, debit_attendu_kbps: int) -> str:
    """
    Derives a probable cause from the NetScan technical data.
    Fallback used instead of / while waiting for the LLM module.
    """
    # Max attainable rate too low -> infrastructure problem
    if measurement.max_attainable_rate_kbps and measurement.max_attainable_rate_kbps < debit_attendu_kbps * TOLERANCE_THRESHOLD:
        return (f"Maximum attainable rate ({measurement.max_attainable_rate_kbps} kbps) "
                f"insufficient — {line_type} infrastructure limitation.")

    # Low SNR = unstable line (only meaningful for ADSL/VDSL)
    if measurement.line_snr_margin_down is not None and measurement.line_snr_margin_down < 6:
        return f"Low signal-to-noise margin (SNR) ({measurement.line_snr_margin_down} dB) — unstable line."

    # High attenuation = degraded cable / excessive distance
    if measurement.line_attenuation_down is not None and measurement.line_attenuation_down > 40:
        return f"High line attenuation ({measurement.line_attenuation_down} dB) — degraded cable or excessive distance."

    # Line down
    if measurement.status_training and "Idle" in measurement.status_training:
        return "Line reported down (Idle) at the time of the measurement."

    return f"Insufficient rate for the {line_type} profile — technical cause not determined automatically."


def determine_urgency(failure_rate_percent: float) -> str:
    """Classifies the urgency according to the percentage gap"""
    if failure_rate_percent > 40:
        return "high"
    elif failure_rate_percent > 20:
        return "medium"
    return "low"


def generate_recommendation(line_type: str, measurement: NetscanMeasurement) -> str:
    """Recommended action according to the line type and the measurements"""
    if line_type == "ADSL":
        return "Migration to VDSL or GPON recommended, or a new intervention on the copper cabling."
    elif line_type == "VDSL":
        return "Migration to GPON recommended if the limitation is confirmed over several measurements."
    elif line_type == "GPON":
        return "Check the ONT equipment, the optical splitter or the patch cord."
    return "Technical re-intervention recommended."


# ══════════════════════════════════════════════════
# 3. MAIN VERIFICATION
# ══════════════════════════════════════════════════
def check_compliance():
    db = SessionLocal()

    # Cut-off date: work orders processed at least 14 days ago
    date_limite = datetime.utcnow() - timedelta(days=VERIFICATION_DELAY_DAYS)

    # 1. Work orders in state "Traite" for >= 14 days
    work_orders = db.query(WorkOrder).filter(
        WorkOrder.etat_ot == "Traite",
        WorkOrder.date_etat <= date_limite
    ).all()

    if not work_orders:
        print(f"No processed work order older than {VERIFICATION_DELAY_DAYS} days.")
        db.close()
        return {"nb_conformes": 0, "nb_anomalies": 0, "nb_sans_mesure": 0, "anomalies": []}

    print(f"🔍 D+{VERIFICATION_DELAY_DAYS} verification for {len(work_orders)} work order(s)...")

    compliant_count = 0
    anomaly_count = 0
    without_measurement_count = 0
    anomalies = []

    for rec in work_orders:
        # 2. Latest NetScan measurement of the customer
        measurement = db.query(NetscanMeasurement)\
                   .filter_by(num_appel=rec.num_appel)\
                   .order_by(NetscanMeasurement.timestamp_mesure.desc())\
                   .first()

        if not measurement:
            print(f"⚠️  No NetScan measurement found for customer {rec.num_appel}.")
            without_measurement_count += 1
            continue

        # 3. Compare the expected rate with the actual rate
        debit_attendu_kbps = parse_rate_kbps(rec.debit)
        minimum_threshold       = debit_attendu_kbps * TOLERANCE_THRESHOLD
        line_type           = extract_line_type(rec.ref_demande)

        if measurement.channel_rate_kbps is not None and measurement.channel_rate_kbps < minimum_threshold:
            # ── ANOMALY DETECTED ──
            gap      = debit_attendu_kbps - measurement.channel_rate_kbps
            failure_rate = round((gap / debit_attendu_kbps) * 100, 1)
            urgency    = determine_urgency(failure_rate)
            cause      = determine_probable_cause(measurement, line_type, debit_attendu_kbps)
            recommendation = generate_recommendation(line_type, measurement)

            print(f"❌ Anomaly — {rec.num_appel} ({line_type}): "
                  f"{measurement.channel_rate_kbps} kbps measured / {debit_attendu_kbps} kbps expected "
                  f"({failure_rate}% gap, urgency: {urgency})")

            message = (
                f"Insufficient rate: {measurement.channel_rate_kbps} kbps measured for a {rec.debit} profile "
                f"({failure_rate}% gap). Probable cause: {cause} "
                f"Recommendation: {recommendation}"
            )

            nouveau_log = LogFollowup(
                ref_demande=rec.ref_demande,
                statut_test="ANOMALIE",
                message_log=message
            )
            db.add(nouveau_log)
            anomaly_count += 1
            anomalies.append({
                "ref_demande": rec.ref_demande,
                "num_appel": rec.num_appel,
                "urgence": urgency,
                "message": message
            })

        else:
            # ── COMPLIANT: no log recorded ──
            print(f"✅ Compliant — {rec.num_appel}: {measurement.channel_rate_kbps} kbps "
                  f"({rec.debit} profile) — not persisted in the database")
            compliant_count += 1

    try:
        db.commit()
        print(f"\n💾 Done: {compliant_count} compliant, {anomaly_count} anomalies recorded, "
              f"{without_measurement_count} without an available measurement.")
    except Exception as e:
        print(f"❌ Error while saving the logs: {e}")
        db.rollback()
    finally:
        db.close()

    return {
        "nb_conformes": compliant_count,
        "nb_anomalies": anomaly_count,
        "nb_sans_mesure": without_measurement_count,
        "anomalies": anomalies
    }


if __name__ == "__main__":
    check_compliance()
