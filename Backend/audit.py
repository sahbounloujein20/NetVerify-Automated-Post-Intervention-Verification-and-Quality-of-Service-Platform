import numpy as np
import pandas as pd
from sqlalchemy.orm import sessionmaker
from database import engine, WorkOrder, NetscanMeasurement, LogFollowup
# Scikit-Learn imports
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
# Database session initialisation
SessionLocal = sessionmaker(bind=engine)
def extract_and_prepare_data():
    """Fetches the real data and prepares the training table."""
    db = SessionLocal()
    print("🔌 Reading the real data from telecom_mock.db...")
    # Join between the work orders and their associated measurements
    records = db.query(WorkOrder, NetscanMeasurement)\
                        .join(NetscanMeasurement, WorkOrder.num_appel == NetscanMeasurement.num_appel)\
                        .all()
    db.close()

    if len(records) < 10:
        raise ValueError("❌ Not enough data to train the model.")

    data = []
    for rec, measurement in records:
        # Convert the text (e.g. "20 mbps") into a number (20480 kbps)
        try:
            debit_chiffre = int(''.join(filter(str.isdigit, rec.debit)))
            debit_attendu_kbps = debit_chiffre * 1024
        except ValueError:
            debit_attendu_kbps = 10240

        debit_reel = measurement.channel_rate_kbps
        snr = measurement.line_snr_margin_down if measurement.line_snr_margin_down else 0.0
        attenuation = measurement.line_attenuation_down if measurement.line_attenuation_down else 0.0
        sync_status = 1 if (measurement.status_training and "Showtime" in measurement.status_training) else 0

        # Labelling rule (our expert rule)
        compliant_threshold = debit_attendu_kbps * 0.9
        if debit_reel >= compliant_threshold and snr >= 6.0 and sync_status == 1:
            label = 0  # OK
        else:
            label = 1  # ANOMALY

        data.append({
            "debit_attendu": debit_attendu_kbps,
            "debit_reel": debit_reel,
            "snr": snr,
            "attenuation": attenuation,
            "statut_synchro": sync_status,
            "label_anomalie": label
        })

    return pd.DataFrame(data)

def train_model():
    """Trains the Scikit-Learn decision tree."""
    df = extract_and_prepare_data()
    # Choice of input variables (features) and output variable (target)
    X = df[["debit_attendu", "debit_reel", "snr", "attenuation", "statut_synchro"]]
    y = df["label_anomalie"]

    # 80% training / 20% validation split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Decision tree training
    model = DecisionTreeClassifier(max_depth=4, random_state=42)
    model.fit(X_train, y_train)

    # Validation of the model's success rate
    predictions = model.predict(X_test)
    precision = accuracy_score(y_test, predictions)
    print(f"🎯 Model accuracy on your real data: {precision * 100:.2f}%\n")

    return model

def run_audit():
    """Runs the automatic audit of the case files."""
    ai_model = train_model()
    if not ai_model:
        return

    db = SessionLocal()
    processed_work_orders = db.query(WorkOrder).filter_by(etat_ot="Traite").all()
    for rec in processed_work_orders:
        db.query(LogFollowup).filter_by(ref_demande=rec.ref_demande).delete()

        # 2. Retrieve the most recent NetScan measurement
        measurement = db.query(NetscanMeasurement)\
                   .filter_by(num_appel=rec.num_appel)\
                   .order_by(NetscanMeasurement.timestamp_mesure.desc())\
                   .first()

        if measurement:
            try:
                debit_chiffre = int(''.join(filter(str.isdigit, rec.debit)))
                debit_attendu_kbps = debit_chiffre * 1024
            except ValueError:
                debit_attendu_kbps = 10240

            debit_reel = measurement.channel_rate_kbps
            snr = measurement.line_snr_margin_down if measurement.line_snr_margin_down else 0.0
            attenuation = measurement.line_attenuation_down if measurement.line_attenuation_down else 0.0
            sync_status = 1 if (measurement.status_training and "Showtime" in measurement.status_training) else 0

            # Build the feature vector for the model
            vecteur_client = np.array([[debit_attendu_kbps, debit_reel, snr, attenuation, sync_status]])

            # Prediction: 0 (OK) or 1 (ANOMALY)
            prediction = ai_model.predict(vecteur_client)[0]
            probabilites = ai_model.predict_proba(vecteur_client)[0]
            certitude = probabilites[prediction] * 100

            if prediction == 1:
                message = (
                    f"Physical anomaly detected (confidence: {certitude:.1f}%). "
                    f"Measured rate: {debit_reel} kbps instead of the expected {debit_attendu_kbps} kbps. "
                    f"SNR: {snr} dB, attenuation: {attenuation} dB."
                )
                print(f"❌ ALERT: {rec.num_appel} - {message}")
                # Write the anomaly report to the database
                nouveau_log = LogFollowup(
                    ref_demande=rec.ref_demande,
                    statut_test="ANOMALIE",
                    message_log=message
                )
                db.add(nouveau_log)
            else:
                print(f"✅ COMPLIANT: {rec.num_appel} - line stable at {debit_reel} kbps (confidence: {certitude:.1f}%)")
        else:
            print(f"⚠️ No NetScan measurement found for {rec.num_appel}.")

    db.commit()
    db.close()
    print("\n💾 Anomalies saved successfully.")

if __name__ == "__main__":
    run_audit()
