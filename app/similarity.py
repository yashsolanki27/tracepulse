from models import Ticket


def find_similar(db, ticket: Ticket, limit: int = 5) -> list[tuple[Ticket, float]]:
    """Top-N resolved incidents by cosine similarity (pgvector <=>).

    Uses the pgvector SQLAlchemy type's cosine_distance(), which binds the
    query vector correctly (no raw list passed to SQL).
    """
    if ticket.embedding is None:
        return []
    distance = Ticket.embedding.cosine_distance(ticket.embedding).label("distance")
    rows = (
        db.query(Ticket, distance)
        .filter(
            Ticket.resolution_text.isnot(None),
            Ticket.embedding.isnot(None),  # NULL vectors make <=> return NULL
            Ticket.id != ticket.id,
        )
        .order_by(distance)
        .limit(limit)
        .all()
    )
    return [(t, 1.0 - d) for t, d in rows]