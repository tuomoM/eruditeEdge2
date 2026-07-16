import hashlib
import json

from Services.vocabulary_contexts import (
    VOCABULARY_REGISTER_CONTEXTS,
    VOCABULARY_USAGE_CONTEXTS,
)
from Services.vocabulary_domains import MAX_VOCABULARY_DOMAINS, VOCABULARY_DOMAINS


PROMPT_TEMPLATE_VERSION = "categorization-maintenance-v1"
DOMAIN_MODEL_PROMPT_TEMPLATE_VERSION = "domain-model-discovery-v1"
RESPONSE_SCHEMA_VERSION = "categorization-maintenance-response-v1"
VALIDATOR_VERSION = "categorization-maintenance-validator-v1"
FREQUENCY_RUBRIC_VERSION = "educated-reader-frequency-v1"

MAINTENANCE_FREQUENCY_BANDS = [
    "common",
    "occasional",
    "specialized",
    "literary",
    "rare",
    "archaic_or_obsolete",
]

PROMPT_TEMPLATE = """
Reassess vocabulary classification for the exact word sense represented by the
entry. Propose ordered semantic domains, context labels, and educated-reader
frequency. Do not rewrite the definition, examples, sources, synonyms, or cloze
sentences. Prefer specific primary domains and avoid broad fallback choices.
""".strip()

DOMAIN_MODEL_PROMPT_TEMPLATE = """
Analyze a vocabulary collection and propose a semantic domain model that is
separate from register, usage context, source, and frequency. The model should
support future graph navigation between domains.
""".strip()


def taxonomy_snapshot():
    return {
        "version": PROMPT_TEMPLATE_VERSION,
        "domains": list(VOCABULARY_DOMAINS),
        "max_domain_count": MAX_VOCABULARY_DOMAINS,
        "domain_rules": {
            "primary_domain": (
                "The domain in which an educated learner is most likely to need "
                "contextual help recognizing this word today."
            ),
            "secondary_domains": (
                "Meaningful alternate learning contexts, not every possible association."
            ),
            "inclusion": [
                "Use 1 to max_domain_count domains.",
                "Put the strongest learning domain first.",
                "Prefer concrete semantic fit over etymological association.",
            ],
            "exclusion": [
                "Do not pad the list with loosely related domains.",
                "Do not use context labels as semantic domains.",
                "Do not use broad categories when a more precise domain fits.",
            ],
        },
        "context_labels": {
            "registers": list(VOCABULARY_REGISTER_CONTEXTS),
            "usage_domains": list(VOCABULARY_USAGE_CONTEXTS),
            "rules": [
                "Choose at least one register label.",
                "Add zero or more usage-domain labels when they clearly help filtering.",
                "Never use General.",
            ],
        },
    }


def frequency_rubric_snapshot():
    return {
        "version": FREQUENCY_RUBRIC_VERSION,
        "bands": {
            "common": "Ordinary adult-reader vocabulary.",
            "occasional": "Known to many educated readers, but not everyday.",
            "specialized": "Common inside a domain, uncommon generally.",
            "literary": "Encountered mainly in literature or serious prose.",
            "rare": "Low encounter likelihood even for educated readers.",
            "archaic_or_obsolete": "Primarily historical, obsolete, or archaic use.",
        },
        "guidance": [
            "Estimate educated-reader encounter likelihood, not model familiarity.",
            "Name the likely encounter context in the rationale.",
            "Do not mark concrete but less everyday words as common merely because they appear in training data.",
        ],
        "examples": {
            "awning": "Usually occasional, not automatically common.",
            "loam": "Often specialized or literary depending on sense and learner context.",
        },
    }


def prompt_template_hash():
    return hashlib.sha256(PROMPT_TEMPLATE.encode("utf-8")).hexdigest()


def domain_model_prompt_template_hash():
    return hashlib.sha256(DOMAIN_MODEL_PROMPT_TEMPLATE.encode("utf-8")).hexdigest()


def stable_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
