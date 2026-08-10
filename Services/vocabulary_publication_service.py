INDEXABLE_PARTS_OF_SPEECH = {
    "noun",
    "verb",
    "adjective",
    "adverb",
    "phrase",
}


def public_index_exclusion_reasons(entry):
    reasons = []
    if not (entry.get("word") or "").strip():
        reasons.append("missing word")
    if not (entry.get("definition") or "").strip():
        reasons.append("missing definition")
    if entry.get("part_of_speech") not in INDEXABLE_PARTS_OF_SPEECH:
        reasons.append("missing specific part of speech")
    if (entry.get("needs_attention") or "").strip():
        reasons.append("needs attention")
    if entry.get("confidence_score") is not None and entry.get("confidence_obsolete"):
        reasons.append("obsolete confidence")
    if not entry.get("examples") and len(entry.get("synonyms") or []) < 2:
        reasons.append("needs example or at least two synonyms")
    return reasons


def is_public_indexable_entry(entry):
    return not public_index_exclusion_reasons(entry)


def is_public_indexable_word(entries):
    return any(is_public_indexable_entry(entry) for entry in entries)
