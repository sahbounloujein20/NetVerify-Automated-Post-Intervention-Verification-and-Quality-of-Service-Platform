"""
scheduler.py — Daily automation
Project: NetVerify — Tunisie Telecom

This script runs in the background and automatically executes:
1. The NetScan simulator (new measurements for every customer)
2. The comparator (D+14 verification of processed work orders)

Run with: python scheduler.py
Leave the window open — the script runs continuously.
"""

from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

from database import SessionLocal, Client
from netscan_simulator import run_single_measurement
from comparator import check_compliance
# TASK 1 — Refresh the NetScan measurements of every customer
def refresh_all_measurements():
    """
    Runs a new NetScan measurement for every customer in the database.
    Mimics the behaviour of a real network supervision system that polls
    the equipment on a regular basis.
    """
    print(f"\n[{datetime.now()}] Refreshing NetScan measurements...")

    db = SessionLocal()
    clients = db.query(Client).all()
    db.close()

    for client in clients:
        try:
            run_single_measurement(client.num_telephone)
        except Exception as e:
            print(f"  ⚠️ Measurement error for {client.num_telephone}: {e}")

    print(f"  → {len(clients)} measurements refreshed.\n")
# TASK 2 — Compliance verification (D+14)
def run_verification():
    """Runs the comparator to detect anomalies."""
    print(f"\n[{datetime.now()}] Starting the compliance verification...")
    check_compliance()
# SCHEDULER CONFIGURATION
def start():
    scheduler = BlockingScheduler()

    # Refresh the measurements every hour
    scheduler.add_job(
        refresh_all_measurements,
        trigger="interval",
        hours=1,
        id="rafraichir_mesures",
        next_run_time=datetime.now()   # run once immediately
    )

    # Check compliance once a day (e.g. every day at 6 a.m.)
    scheduler.add_job(
        run_verification,
        trigger="cron",
        hour=12,
        minute=11,
        id="verification_quotidienne"
    )
    print("=" * 55)
    print("  NetVerify Scheduler — started")
    print("=" * 55)
    print("  • NetScan measurements : hourly")
    print("  • D+14 verification    : every day at 06:00")
    print("  Ctrl+C to stop")
    print("=" * 55)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nScheduler stopped.")
if __name__ == "__main__":
    start()
