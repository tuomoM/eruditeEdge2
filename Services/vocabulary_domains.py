import json
from sqlite3 import OperationalError

import db


VOCABULARY_DOMAINS = (
    "emotion",
    "attitude",
    "cognition",
    "communication",
    "morality",
    "justice",
    "power",
    "society",
    "status",
    "conflict",
    "violence",
    "time",
    "change",
    "certainty",
    "perception",
    "appearance",
    "quality",
    "relation",
    "degree",
    "movement",
    "quantity",
    "causation",
    "judgment",
    "reasoning",
    "truth",
    "rhetoric",
    "literature",
    "religion",
    "body",
)

MAX_VOCABULARY_DOMAINS = 4


def active_vocabulary_domains():
    try:
        rows = db.query(
            """
            SELECT proposal_json
            FROM vocabulary_domain_model_proposals
            WHERE status = 'accepted'
            ORDER BY COALESCE(reviewed_at, created_at) DESC, id DESC
            LIMIT 1
            """
        )
    except (OperationalError, RuntimeError):
        return VOCABULARY_DOMAINS
    if not rows:
        return VOCABULARY_DOMAINS

    try:
        proposal = json.loads(rows[0]["proposal_json"])
    except (TypeError, json.JSONDecodeError):
        return VOCABULARY_DOMAINS

    domains = []
    seen_domains = set()
    for domain in proposal.get("domains", []):
        key = str(domain.get("key") if isinstance(domain, dict) else domain).strip()
        if key and key not in seen_domains:
            domains.append(key)
            seen_domains.add(key)
    return tuple(domains) or VOCABULARY_DOMAINS
