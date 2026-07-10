VOCABULARY_REGISTER_CONTEXTS = [
    "Informal",
    "Formal",
    "Literary",
    "Technical",
    "Archaic",
    "Dialectal",
]

VOCABULARY_USAGE_CONTEXTS = [
    "Academic",
    "Business",
    "Legal",
    "Medical",
    "Biology",
    "Science",
    "Philosophy",
    "Religion",
    "Military",
    "Geography",
]

VOCABULARY_CONTEXTS = VOCABULARY_REGISTER_CONTEXTS + VOCABULARY_USAGE_CONTEXTS
MAX_VOCABULARY_CONTEXTS = len(VOCABULARY_CONTEXTS)

_CONTEXT_ALIASES = {
    "business english": "Business",
    "casual": "Informal",
    "colloquial": "Informal",
    "everyday": "Informal",
    "historical": "Archaic",
    "poetic": "Literary",
    "professional": "Formal",
    "religious": "Religion",
    "scientific": "Science",
}

_CONTEXTS_BY_LOWER = {
    context.lower(): context
    for context in VOCABULARY_CONTEXTS
}


def normalize_contexts(value):
    contexts = []
    for raw_context in _raw_context_parts(value):
        context = _canonical_context(raw_context)
        if context and context not in contexts:
            contexts.append(context)
        if len(contexts) >= MAX_VOCABULARY_CONTEXTS:
            break
    return [
        context
        for context in contexts
        if context in VOCABULARY_REGISTER_CONTEXTS
    ] + [
        context
        for context in contexts
        if context in VOCABULARY_USAGE_CONTEXTS
    ]


def normalize_context_string(value):
    return "; ".join(normalize_contexts(value))


def _raw_context_parts(value):
    if isinstance(value, (list, tuple)):
        values = value
    else:
        values = str(value or "").replace("/", ";").replace(",", ";").split(";")
    return [" ".join(str(item).strip().split()) for item in values if str(item).strip()]


def _canonical_context(value):
    normalized = " ".join(str(value or "").strip().split())
    if not normalized:
        return None
    lowered = normalized.lower()
    if lowered == "general":
        return None
    if lowered in _CONTEXT_ALIASES:
        return _CONTEXT_ALIASES[lowered]
    if lowered in _CONTEXTS_BY_LOWER:
        return _CONTEXTS_BY_LOWER[lowered]
    return None
