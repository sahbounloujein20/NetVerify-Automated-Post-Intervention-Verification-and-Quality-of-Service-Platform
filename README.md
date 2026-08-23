
</p>
 <p align="center">
  <img  src="assets/Tunisietelecom.jpg" alt="NetVerify - Tunisie Telecom" width="180">
</p>

<h1 align="center">NetVerify</h1>

<p align="center"><b>Automated Post-Intervention Verification and Quality-of-Service Platform</b></p>

> Developed for **Tunisie Telecom** (Unit Management of Services -- Hached Complex) in collaboration with **ENSI** (National School of Computer Sciences, University of Manouba).

---

## 📖 Overview

**NetVerify** is an end-to-end automated Quality of Service (QoS) audit platform designed to close the loop on fixed broadband claims (ADSL, VDSL, GPON). 

In traditional telecom workflows, when a field technician resolves a customer complaint, the ticket is marked "Resolved" (Traité) and closed. However, there is rarely any systematic verification to check if the line actually delivers the speed sold to the customer. This gap leads to unresolved physical issues, customer frustration, and recurring tickets.

NetVerify solves this by auditing lines **14 days (D+14)** after ticket closure. It queries physical parameters (sync rate, noise margin, attenuation) using a NetScan line-supervision mock simulator, runs the metrics through a **Scikit-Learn Machine Learning classifier** to predict compliance and diagnose root causes, and uses **n8n workflows** to orchestrate daily audits and route alerts to technical teams (via Slack and Email).

---

## 🚀 Key Features

*   **Automated Audit Pipeline (D+14):** Automatically queries resolved claims that have been closed for 14 days (time needed for line stabilization).
*   **NetScan Line Telemetry Integration:** Extracts physical parameters like sync rate, maximum attainable speed, SNR margin (down/up), line attenuation, and training status.
*   **Machine Learning Diagnostics:** Integrates a Scikit-Learn `DecisionTreeClassifier` to classify line status (Compliant vs. Anomaly) and calculate diagnostic confidence scores.
*   **n8n Workflow Orchestration:** Schedules audits daily, handles loops, runs asynchronous line tests, and dispatches multi-channel alerts (Slack channel posts + HTML emails).
*   **Interactive Streamlit Dashboard:** Features operational KPI monitoring, 3D cartography of Grand Tunis, technician resolution rate rankings, ISP comparative performance analytics, and database integrity audits.
*   **RESTful FastAPI Backend:** Fully-secured FastAPI engine with OAuth2/JWT authentication, rate limiting, and role-based access control (`technicien`, `superviseur`, `service`).

---

## 🛠️ Technology Stack

| Layer | Technologies | Role in the Platform |
| :--- | :--- | :--- |
| **Frontend** | Streamlit, Plotly, Pandas, Pydeck | Operator workspace, charts, 3D geographic maps, reporting interface |
| **Backend** | FastAPI, Python 3.11, Pydantic, Uvicorn | RESTful API endpoints, request validation, business logic orchestration |
| **Persistence** | PostgreSQL, SQLAlchemy 2.0 | Relational database (Clients, Technicians, Claims, NetScan measurements, Logs) |
| **Orchestration** | n8n | Scheduler, webhook handlers, loop batches, Slack/SMTP notification routing |
| **ML Engine** | Scikit-Learn | Decision Tree model training (`audit.py`) and anomaly classification |
| **Containerization**| Docker, Docker Compose | Microservices orchestration and environment reproducibility |

---

## 📐 System Architecture

NetVerify follows a decoupled, three-tier architecture that can be deployed entirely local or inside Docker containers.

```mermaid
flowchart TD
    subgraph frontend ["Streamlit Frontend [Port 8501]"]
        A[Dashboard UI]
        B[Geolocated Maps]
    end
    subgraph backend ["FastAPI Backend [Port 8000]"]
        C[REST API Engine]
        D[Scikit-Learn DecisionTree]
    end
    subgraph database ["Database Layer [Port 5432]"]
        E[(PostgreSQL DB)]
    end
    subgraph automation ["Automation Layer [Port 5678]"]
        F[n8n Workflow Engine]
    end

    A <-->|REST Calls / JSON| C
    C <-->|SQLAlchemy ORM| E
    F -->|HTTP POST Verification| C
    F -.->|Alert Routing| G[Slack Channel / Email]
```

### The n8n Audit Loop:
The background verification cycle runs daily at 08:00 AM using the following automated sequence:

```mermaid
stateDiagram-v2
    [*] --> ScheduleTrigger
    ScheduleTrigger --> GetClaims : GET /reclamations-a-verifier
    GetClaims --> HasClaims?
    
    state HasClaims? {
        [*] --> IfClaimsExist
        IfClaimsExist --> LoopOverClaims : Yes (Claims > 0)
        IfClaimsExist --> EndWorkflow : No
    }
    
    state LoopOverClaims {
        [*] --> TriggerNetscan : POST /mesures/rafraichir
        TriggerNetscan --> FetchQoSStatus : GET /reclamations/{ref_demande}
        FetchQoSStatus --> IsAnomaly?
        
        state IsAnomaly? {
            [*] --> IfAnomalyFlagged
            IfAnomalyFlagged --> SendAlerts : Yes (ANOMALIE)
            IfAnomalyFlagged --> NextClaim : No (CONFORME)
        }
    }
    
    SendAlerts --> LoopOverClaims : Next batch item
    NextClaim --> LoopOverClaims : Next batch item
    LoopOverClaims --> [*] : All items processed
```

---

## 🗄️ Database Design

The PostgreSQL database (`telecom_db`) contains the following key tables:

```mermaid
erDiagram
    clients ||--o{ reclamations_workflow : "declares"
    clients ||--o{ mesures_netscan : "undergoes"
    techniciens ||--o{ reclamations_workflow : "resolves"
    reclamations_workflow ||--o{ logs_followup : "generates"

    clients {
        string num_telephone PK
        string nom_client
        string techno_souscrite "ADSL / VDSL / GPON"
    }

    techniciens {
        string id_technicien PK
        string nom_technicien
        string telephone_pro
    }

    reclamations_workflow {
        string ref_demande PK "Format: TECH/YEAR/SEQ"
        string num_appel FK
        string debit "Subscribed Profile (e.g. 20 mbps)"
        string fsi "ISP Name"
        string etat_ot "Emis / En cours / Traite"
        datetime date_etat
        string id_technicien FK
    }

    mesures_netscan {
        int id_mesure PK
        string num_appel FK
        datetime timestamp_mesure
        int channel_rate_kbps "Modem Sync Rate"
        int max_attainable_rate_kbps "Line Max Capacity"
        float line_snr_margin_down "SNR Margin"
        float line_attenuation_down "Line Attenuation"
        string status_training "Showtime / Idle"
    }

    logs_followup {
        int id_log PK
        string ref_demande FK
        datetime date_test
        string statut_test "ANOMALIE / CONFORME"
        string message_log "Diagnostic Message"
    }
```

---

## 🧠 Machine Learning Audit Logic

Instead of basic threshold checks, NetVerify trains a Scikit-Learn `DecisionTreeClassifier` on historical network loops. The model acts as an auditing agent:

1.  **Features (`X`):** `[debit_attendu, debit_reel, snr, attenuation, statut_synchro]`
2.  **Target Label (`y`):** `0` (Compliant) or `1` (Anomaly).
3.  **Labeling Criteria:** Lines are labeled compliant if `debit_reel` $\ge$ 90% of `debit_attendu`, `snr` $\ge$ 6.0 dB, and `statut_synchro` is Showtime (1).
4.  **Inference:** For each resolved work order (OT), the model runs prediction and extracts the probability using `predict_proba()`. If an anomaly is predicted, a diagnostic log is recorded containing the model's confidence level (e.g., *"Physical anomaly detected with 100% confidence"*).

---

## ⚙️ Installation & Setup

### Prerequisites
*   Python 3.11+
*   PostgreSQL 14+
*   n8n Workflow Engine
*   Docker & Docker Compose (optional for containerized deployment)

### Local Setup

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/yourusername/NetVerify.git
    cd NetVerify
    ```

2.  **Create and Activate Virtual Environment:**
    ```bash
    python -m venv venv
    # On Windows:
    .\venv\Scripts\activate
    # On Linux/macOS:
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r Backend/requirements.txt
    ```

4.  **Configure Environment Variables:**
    Create a `.env` file in the root directory (and inside the `Backend/` directory) and specify:
    ```env
    DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/telecom_db
    JWT_SECRET=your_jwt_secret_key_here
    ```

5.  **Initialize and Seed the Database:**
    Ensure PostgreSQL is running and your database (`telecom_db`) exists, then execute:
    ```bash
    cd Backend
    python BaseDonne.py
    ```
    *This creates the relational tables and populates them with 500 mock clients, technicians, and work orders distributed across Grand Tunis.*

6.  **Create an Administrator Account:**
    ```bash
    python gerer_utilisateurs.py creer --identifiant admin --nom "Supervisor Name" --role superviseur
    ```

7.  **Run the FastAPI Backend:**
    ```bash
    python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
    ```

8.  **Run the Streamlit Frontend:**
    In a new terminal window (with activated virtual environment):
    ```bash
    cd frontend
    streamlit run dashboard.py
    ```
    *Open your browser and navigate to `http://localhost:8501`.*

9.  **Import n8n Workflow:**
    *   Open your n8n workspace (e.g. `http://localhost:5678`).
    *   Create a new workflow, click the top-right menu, select **Import from File**, and upload:
        *   `n8n/n8n_workflow_netverify_no_credentials.json` (For local testing without SMTP/Slack credentials).
        *   `n8n/n8n_workflow_netverify_advanced.json` (For production with SMTP/Slack configurations).
    *   Ensure your FastAPI server is running on port 8000 and click **Execute workflow**.

---

## 🐳 Docker Deployment

NetVerify is fully packaged to run inside a multi-container Docker stack:

```bash
docker-compose up --build -d
```
This builds and launches:
*   `backend`: FastAPI service running on port `8000`.
*   `frontend`: Streamlit dashboard running on port `8501`.
*   `postgres`: Relational database mapping port `5432`.

---



## 📄 License
This project is developed as part of an end-of-studies graduation project. All rights reserved by Tunisie Telecom.
