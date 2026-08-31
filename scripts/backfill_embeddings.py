"""One-off: backfill embeddings for tickets with embedding IS NULL.

Run inside the api container (model + DB access live there):
    docker exec -i <api-container> python - < scripts/backfill_embeddings.py
Same approach used for ticket 1 in Phase 6, generalized.
"""
from database import SessionLocal
from models import Ticket
from embeddings import embed_ticket

db = SessionLocal()
try:
    rows = db.query(Ticket).filter(Ticket.embedding.is_(None)).all()
    for t in rows:
        t.embedding = embed_ticket(t.title, t.description)
        print(f"id={t.id} embedded={t.embedding is not None}")
    db.commit()
    print("backfill complete")
finally:
    db.close()
