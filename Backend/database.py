from sqlalchemy import (
    create_engine, Column, Boolean, Integer, String, Float, DateTime, ForeignKey
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime, timedelta
import os
import random
import sys

# ==========================================
# 1. POSTGRESQL DATABASE CONFIGURATION
# ==========================================
# Format: postgresql://user:password@host:port/database_name
#
# The URL comes from the environment. The local fallback keeps the project
# runnable with a plain `python main.py`, but it carries a development password
# written into the repository: every deployment MUST set NETVERIFY_DATABASE_URL,
# and the warning below is a reminder on every start without the variable.
_DEV_URL = "postgresql://postgres:/telecom_db"
DATABASE_URL = os.environ.get("NETVERIFY_DATABASE_URL", "").strip()

if not DATABASE_URL:
    DATABASE_URL = _DEV_URL
    print(
        "[database] NETVERIFY_DATABASE_URL is missing: falling back to the local "
        "development database, whose password is written in the source code. "
        "Never use this in production.",
        file=sys.stderr,
    )

engine = create_engine(DATABASE_URL, echo=False)
Base = declarative_base()

# ==========================================
# 2. TABLE DEFINITIONS (ORM MODELS)
# ==========================================

class Client(Base):
    """Customer reference table"""
    __tablename__ = 'clients'

    num_telephone = Column(String(20), primary_key=True)
    nom_client = Column(String(100), nullable=False)
    techno_souscrite = Column(String(20), nullable=False) # ADSL, VDSL, GPON

    # Relationships
    work_orders = relationship("WorkOrder", back_populates="client")
    netscan_measurements = relationship("NetscanMeasurement", back_populates="client")

class Technician(Base):
    """Tunisie Telecom / subcontractor technicians table"""
    __tablename__ = 'techniciens'

    id_technicien = Column(String(50), primary_key=True)
    nom_technicien = Column(String(100), nullable=False)
    telephone_pro = Column(String(20))

    # Relationships
    work_orders = relationship("WorkOrder", back_populates="technician")

class WorkOrder(Base):
    """Work-order (OT) tracking table (Workflow Backbone)"""
    __tablename__ = 'reclamations_workflow'

    ref_demande = Column(String(50), primary_key=True)
    num_appel = Column(String(20), ForeignKey('clients.num_telephone'))
    position_site_ancienne = Column(String(255))
    position_site_nouvelle = Column(String(255))
    position_rla = Column(String(255), nullable=True)
    debit = Column(String(20))
    fsi = Column(String(50))
    type_demande = Column(String(100))
    type_ot = Column(String(100))
    etat_ot = Column(String(50))
    date_etat = Column(DateTime)

    id_technicien = Column(String(50), ForeignKey('techniciens.id_technicien'), nullable=True)

    # Relationships
    client = relationship("Client", back_populates="work_orders")
    technician = relationship("Technician", back_populates="work_orders")
    followup_logs = relationship("LogFollowup", back_populates="work_order")

class NetscanMeasurement(Base):
    """Physical line parameters table (NetScan)"""
    __tablename__ = 'mesures_netscan'

    id_mesure = Column(Integer, primary_key=True, autoincrement=True)
    num_appel = Column(String(20), ForeignKey('clients.num_telephone'))
    timestamp_mesure = Column(DateTime, nullable=False, default=datetime.utcnow)

    distance_approx_km = Column(Float)
    total_output_power_dbm = Column(Float)
    signal_attenuation_down = Column(Float)
    signal_attenuation_up = Column(Float)
    line_attenuation_down = Column(Float)
    line_attenuation_up = Column(Float)
    line_snr_margin_down = Column(Float)
    line_snr_margin_up = Column(Float)
    max_attainable_rate_kbps = Column(Integer)
    channel_rate_kbps = Column(Integer)
    status_training = Column(String(50))

    # Relationships
    client = relationship("Client", back_populates="netscan_measurements")

class User(Base):
    """Accounts allowed to open the platform.

    A table distinct from `techniciens`: a technician is an operational
    resource that exists whether or not they ever sign in, whereas a user is an
    access. Not all 500 technicians of the referential need to open the
    dashboard, and a supervisor who works on no work order must still be able
    to sign in. `id_technicien` links the two when they are the same person.

    The password is never stored: only its bcrypt hash is.
    """
    __tablename__ = 'utilisateurs'

    identifiant = Column(String(50), primary_key=True)
    nom_complet = Column(String(100), nullable=False)
    mot_de_passe_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default='technicien')
    actif = Column(Boolean, nullable=False, default=True)
    date_creation = Column(DateTime, nullable=False, default=datetime.utcnow)
    derniere_connexion = Column(DateTime, nullable=True)

    id_technicien = Column(String(50), ForeignKey('techniciens.id_technicien'), nullable=True)

    technician = relationship("Technician")


class LogFollowup(Base):
    """Results table of the validation script"""
    __tablename__ = 'logs_followup'

    id_log = Column(Integer, primary_key=True, autoincrement=True)
    ref_demande = Column(String(50), ForeignKey('reclamations_workflow.ref_demande'))
    date_test = Column(DateTime, nullable=False, default=datetime.utcnow)
    statut_test = Column(String(50), nullable=False)
    message_log = Column(String, nullable=False)

    # Relationships
    work_order = relationship("WorkOrder", back_populates="followup_logs")


class AuditEntry(Base):
    """Journal of the privileged actions.

    Restricting an action is only half a control: without a trace, nobody can
    say afterwards which supervisor launched the estate-wide verification at
    14:03, nor that an unauthorised account tried. This table is that second
    half — it records the attempts as well as the successes.

    Distinct from `logs_followup`, which journals what the *business* control
    found: here we journal who *asked* for it. No foreign key to
    `utilisateurs`: the author may be the n8n automaton, which owns no account,
    and a trace must survive the deletion of the account it names.
    """
    __tablename__ = 'journal_actions'

    id_action = Column(Integer, primary_key=True, autoincrement=True)
    horodatage = Column(DateTime, nullable=False, default=datetime.utcnow)
    # Login of the human, or "n8n (service token)" for the automaton.
    auteur = Column(String(100), nullable=False)
    role = Column(String(20))
    action = Column(String(120), nullable=False)   # path of the endpoint called
    resultat = Column(String(20), nullable=False)  # succes | echec | refus
    details = Column(String)

# ==========================================
# 3. PHYSICAL DATABASE CREATION AND SEEDING
# ==========================================
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

def generate_mock_data():
    """Generates 500 customers, technicians and work orders for the mock-up."""


    if db.query(Client).first():
        print("✅ Data already exists in the PostgreSQL database. No insertion needed.")
        db.close()
        return



    PRENOMS = ["Mohamed", "Ahmed", "Youssef", "Anis", "Kais", "Amine", "Hamza", "Khaled", "Karim", "Sami", "Sonia", "Meriam", "Olfa", "Fatma"]
    NOMS = ["Trabelsi", "Gharbi", "Chaari", "Bouazizi", "Ben Ali", "Mansouri", "Dridi", "Ayari", "Amri", "Kouki"]
    FSIS = ["Topnet", "GlobalNet", "FSI TT", "Hexabyte", "Bee"]
    TECHNOS = ["ADSL", "VDSL", "GPON"]
    # The values below are stored as-is in the database: they reproduce the
    # vocabulary of the operator's own systems and must not be translated.
    REQUEST_TYPES = ["Réclamation", "Augmentation", "Migration"]
    WORK_ORDER_TYPES = ["Dérangement", "Changement Profil", "Basculement Port"]
    WORK_ORDER_STATUSES = ["Emis", "En cours", "Traite"]

    def generate_phone():
        prefix = random.choice(["71", "73", "98", "22", "55"])
        number = "".join([str(random.randint(0, 9)) for _ in range(6)])
        return f"{prefix}{number}"

    # 1. Insert technicians
    technicians = []
    for i in range(1, 501):
        tech = Technician(
            id_technicien=f"TECH-{i:03d}",
            nom_technicien=f"{random.choice(PRENOMS)} {random.choice(NOMS)}",
            telephone_pro=generate_phone()
        )
        technicians.append(tech)
    db.add_all(technicians)

    # 2. Insert customers
    clients = []
    for i in range(1, 501):
        client = Client(
            num_telephone=generate_phone(),
            nom_client=f"{random.choice(PRENOMS)} {random.choice(NOMS)}",
            techno_souscrite=random.choice(TECHNOS)
        )
        clients.append(client)
    db.add_all(clients)
    db.commit()

    # 3. Insert work orders & NetScan measurements
    base_date = datetime.utcnow() - timedelta(days=30)
    work_orders = []
    measurements = []

    for i, client in enumerate(clients):
        status = random.choice(WORK_ORDER_STATUSES)
        debit_val = "10 mbps" if client.techno_souscrite == "ADSL" else ("20 mbps" if client.techno_souscrite == "VDSL" else "100 mbps")

        rec = WorkOrder(
            ref_demande=f"{client.techno_souscrite}/2026/15{i:03d}",
            num_appel=client.num_telephone,
            position_site_ancienne=f"MSAN_Ancien_{i}",
            position_site_nouvelle=f"MSAN_Nouveau_{i}",
            debit=debit_val,
            fsi=random.choice(FSIS),
            type_demande=random.choice(REQUEST_TYPES),
            type_ot=random.choice(WORK_ORDER_TYPES),
            etat_ot=status,
            date_etat=base_date + timedelta(days=random.randint(0, 29)),
            id_technicien=random.choice(technicians).id_technicien if status != "Emis" else None
        )
        work_orders.append(rec)

        measurement = NetscanMeasurement(
            num_appel=client.num_telephone,
            timestamp_mesure=datetime.utcnow() - timedelta(minutes=random.randint(1, 60)),
            line_snr_margin_down=round(random.uniform(6.0, 30.0), 1),
            line_attenuation_down=round(random.uniform(5.0, 45.0), 1),
            channel_rate_kbps=10240 if client.techno_souscrite == "ADSL" else (20480 if client.techno_souscrite == "VDSL" else 102400),
            status_training="6 Showtime/Atteint"
        )
        measurements.append(measurement)

    db.add_all(work_orders)
    db.add_all(measurements)
    db.commit()
    db.close()
    print("🚀 Success: 500 customers, 500 technicians and 500 work orders inserted into PostgreSQL!")

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    print("📁 Tables created successfully in PostgreSQL!")
    generate_mock_data()
