from fastapi import Depends
from sqlalchemy.orm import Session

from database import (
    SessionLocal, Client, Technician,
    WorkOrder, NetscanMeasurement, LogFollowup
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
def detect_zones(db: Session = Depends(get_db)):
    zones={"red":[], "orange":[], "green":[]}
    result=db.execute(" select  zone ,count(*) from reclamation_workflow R  logs_followup L" \
   "where R.ref_demande=L.ref_demande" \
   "group by R.zone_reclammation").fetchall()
    for r in result:
        if r[1]*100<10:
         zones["green"].append(r[0])
        elif r[1]*100<50:
         zones["orange"].append(r[0])
        else:
         zones["red"].append(r[0])

