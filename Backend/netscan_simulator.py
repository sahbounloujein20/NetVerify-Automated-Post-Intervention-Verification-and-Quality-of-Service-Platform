import random
from datetime import datetime
from database import Client, NetscanMeasurement

def run_single_measurement(id_client, db):  # 1. 'db' is accepted as a parameter
    """
    Performs a single, immediate measurement for a given customer.
    Reuses the active session handed over by the FastAPI route.
    """
    # 2. Fetch the customer with the parent session
    client = db.query(Client).filter(Client.num_telephone == id_client).first()

    if not client:
        print(f"⚠️ Customer {id_client} not found.")
        return None

    # 3. Retrieve the last existing measurement to keep the series continuous
    latest_measurement = db.query(NetscanMeasurement)\
                        .filter_by(num_appel=client.num_telephone)\
                        .order_by(NetscanMeasurement.timestamp_mesure.desc())\
                        .first()

    # Safe fallback values when no measurement exists yet
    base_rate = latest_measurement.channel_rate_kbps if latest_measurement and latest_measurement.channel_rate_kbps else 10240
    base_snr = latest_measurement.line_snr_margin_down if latest_measurement and latest_measurement.line_snr_margin_down else 12.0
    base_attenuation = latest_measurement.line_attenuation_down if latest_measurement and latest_measurement.line_attenuation_down else 25.0

    # 4. Compute the new values
    if client.techno_souscrite == 'GPON':
        nouveau_rate = base_rate
        nouveau_snr = None
        nouvelle_attenuation = None
        status_value = "UP"
    else:
        nouveau_rate = base_rate + random.choice([-64, 0, 0, 64])
        nouveau_snr = round(base_snr + random.uniform(-0.5, 0.5), 1)
        nouvelle_attenuation = round(base_attenuation + random.uniform(-0.1, 0.1), 1)

        is_down = random.random() < 0.01
        status_value = "6 Showtime/Atteint" if not is_down else "1 Idle/Coupure"
        if is_down: nouveau_rate = 0

    # 5. Store the measurement inside the API session
    new_measurement = NetscanMeasurement(
        num_appel=client.num_telephone,
        timestamp_mesure=datetime.now(),  # records the actual local time
        channel_rate_kbps=nouveau_rate,
        line_snr_margin_down=nouveau_snr,
        line_attenuation_down=nouvelle_attenuation,
        status_training=status_value
    )
    db.add(new_measurement)
    print(f"✅ Measurement prepared for {id_client}: {nouveau_rate} kbps")

    # WARNING: no db.commit() or db.close() here!
