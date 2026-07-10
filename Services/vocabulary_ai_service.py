import json
import logging
import re
import time

from Services.vocabulary_domains import MAX_VOCABULARY_DOMAINS, VOCABULARY_DOMAINS


logger = logging.getLogger(__name__)
WORD_PATTERN = re.compile(r"^[A-Za-z]+(?:[-'][A-Za-z]+)?$")
OPENAI_REQUEST_TIMEOUT_SECONDS = 20
OPENAI_MAX_RETRIES = 1
VOCABULARY_ENTRY_MAX_OUTPUT_TOKENS = 900
CLOZE_DATA_MAX_OUTPUT_TOKENS = 500
SYNONYM_NET_CLOZE_MAX_OUTPUT_TOKENS = 1200
USAGE_VALIDATION_MAX_OUTPUT_TOKENS = 160
MAX_AI_VOCABULARY_DOMAINS = 3
MAX_USAGE_CLUE_LENGTH = 500
FREQUENCY_BANDS = [
    "common",
    "uncommon",
    "rare",
    "very_rare",
    "archaic_or_obsolete",
    "specialized",
]
ALLOWED_CONTEXT_LABELS = {
    "Academic",
    "Archaic",
    "Business",
    "Business English",
    "Casual",
    "Colloquial",
    "Education",
    "Emotional",
    "Equestrian",
    "Everyday",
    "Finance",
    "Formal",
    "General",
    "Historical",
    "Informal",
    "Legal",
    "Literary",
    "Medical",
    "Philosophy",
    "Poetic",
    "Political",
    "Professional",
    "Ranching",
    "Regional",
    "Religious",
    "Rural",
    "Scientific",
    "Social",
    "Technical",
}


VOCABULARY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "word": {"type": "string"},
        "definition": {"type": "string"},
        "context": {
            "type": "string",
            "description": (
                "A short usage setting, category, or register, not an example sentence. "
                "This is separate "
                "from semantic domains and must not describe the word's meaning. "
                "Use 1-4 slash-separated labels such as Formal, Casual, "
                "Medical, Philosophy, Academic, Business English, Business/Formal."
            ),
        },
        "part_of_speech": {
            "type": "string",
            "enum": ["noun", "verb", "adjective", "adverb", "phrase", "other"],
        },
        "frequency_band": {
            "type": "string",
            "enum": FREQUENCY_BANDS,
            "description": (
                "How commonly this exact word sense is used in modern English. "
                "Use specialized for domain-specific senses, very_rare for highly "
                "unusual but current words, and archaic_or_obsolete for historical "
                "or obsolete senses."
            ),
        },
        "frequency_note": {
            "type": "string",
            "description": (
                "One short note explaining frequency or register. Empty only when "
                "frequency_band is common and no note is useful."
            ),
        },
        "domains": {
            "type": "array",
            "items": {"type": "string", "enum": list(VOCABULARY_DOMAINS)},
            "description": (
                "Ordered semantic areas represented by the word's meaning. The first "
                "item is the primary domain. Add secondary and tertiary domains only "
                "when they are clearly represented by the meaning. These are independent "
                "of usage settings such as Academic, Medical, or General."
            ),
        },
        "synonyms": {
            "type": "array",
            "items": {"type": "string"},
        },
        "examples": {
            "type": "array",
            "items": {"type": "string"},
        },
        "cloze_sentences": {
            "type": "array",
            "items": {"type": "string"},
        },
        "needs_attention": {
            "type": "string",
            "description": (
                "Empty when no admin review is needed. Otherwise, a concise "
                "explanation of the uncertainty, at most 200 characters."
            ),
        },
        "confidence_score": {
            "type": "integer",
        },
    },
    "required": [
        "word",
        "definition",
        "context",
        "part_of_speech",
        "frequency_band",
        "frequency_note",
        "domains",
        "synonyms",
        "examples",
        "cloze_sentences",
        "needs_attention",
        "confidence_score",
    ],
}


CLOZE_DATA_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "part_of_speech": {
            "type": "string",
            "enum": ["noun", "verb", "adjective", "adverb", "phrase", "other"],
        },
        "domains": {
            "type": "array",
            "items": {"type": "string", "enum": list(VOCABULARY_DOMAINS)},
        },
        "cloze_sentences": {
            "type": "array",
            "items": {"type": "string"},
        },
        "needs_attention": {
            "type": "string",
        },
        "confidence_score": {
            "type": "integer",
        },
    },
    "required": [
        "part_of_speech",
        "domains",
        "cloze_sentences",
        "needs_attention",
        "confidence_score",
    ],
}


USAGE_VALIDATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "result": {
            "type": "string",
            "enum": ["correct", "incorrect"],
        },
        "hint": {
            "type": "string",
            "description": "Empty when result is correct. One sentence when result is incorrect.",
        },
    },
    "required": ["result", "hint"],
}


SYNONYM_NET_CLOZE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "vocabulary_id": {"type": "integer"},
                    "cloze_sentences": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "needs_attention": {
                        "type": "string",
                        "description": (
                            "Empty when no review is needed. Otherwise, a concise "
                            "explanation of uncertainty, at most 200 characters."
                        ),
                    },
                    "confidence_score": {"type": "integer"},
                },
                "required": [
                    "vocabulary_id",
                    "cloze_sentences",
                    "needs_attention",
                    "confidence_score",
                ],
            },
        },
    },
    "required": ["entries"],
}


class VocabularyAiService:
    def __init__(self, client=None):
        self._client = client

    def generate_entry(self, word, api_key, model, usage_clue=None):
        word, error = self._validate_word(word)
        if error:
            logger.info("Vocabulary AI generation rejected input: %s", error)
            return None, error
        usage_clue, error = self._validate_usage_clue(usage_clue, word)
        if error:
            logger.info("Vocabulary AI generation rejected usage clue: %s", error)
            return None, error
        if not api_key:
            logger.warning("Vocabulary AI generation failed: missing OpenAI API key")
            return None, "OpenAI API key is missing"

        logger.info("Vocabulary AI generation started for word '%s' using model '%s'", word, model)
        try:
            client = self._get_client(api_key)
            started_at = time.perf_counter()
            response = client.responses.create(
                model=model,
                max_output_tokens=VOCABULARY_ENTRY_MAX_OUTPUT_TOKENS,
                store=False,
                instructions=(
                    "Create vocabulary entry data for the provided single word. "
                    "Return only factual dictionary-style data. Do not include HTML. "
                    "If a usage clue is provided, generate the entry for the word "
                    "sense implied by that clue, not the most common sense. Parentheses "
                    "around the word mark the exact occurrence the learner encountered. "
                    "Short hints such as 'a', 'to', 'noun', 'verb', or a subject area "
                    "are valid clues and should influence part of speech and sense. "
                    "The context field must describe the usage setting, category, or "
                    "register, not the word's semantic meaning and not a sentence. "
                    "Examples: Formal, Casual, Medical, Philosophy, Academic, Business "
                    "English, Business/Formal, Literary, Historical, Technical. "
                    "Use General only for words that are genuinely ordinary across "
                    "everyday usage; prefer a more specific register or setting when "
                    "the word is literary, formal, specialized, archaic, technical, "
                    "or source-specific. Keep context separate from domains. "
                    "Domains describe semantic meaning, such as movement, cognition, "
                    "power, or rhetoric. Provide 2-4 example "
                    "sentences that use the word naturally. Identify the primary part "
                    "of speech for this meaning using noun, verb, adjective, adverb, "
                    "phrase, or other. Assign 1-3 ordered semantic domains using only: "
                    f"{', '.join(VOCABULARY_DOMAINS)}. Put the primary domain first. "
                    "Do not pad the domain list with weak or merely associated labels. "
                    "For physical motion words, prefer movement as the primary domain "
                    "over perception unless the meaning is actually about seeing or "
                    "sensing. Classify how common this exact sense is using one "
                    f"frequency band: {', '.join(FREQUENCY_BANDS)}. Provide a short "
                    "frequency note when the sense is not common. Provide 2-3 cloze training "
                    "sentences. Each cloze "
                    "sentence must use exactly one ____ blank where the target word "
                    "belongs, must not include the target word elsewhere, and must be "
                    "natural enough that same-part-of-speech distractors are plausible. "
                    "Return a confidence score from 0 to 100 for the complete entry. "
                    "If any classification or generated content needs admin review, "
                    "put a concise explanation of at most 200 characters in "
                    "needs_attention; otherwise return an empty string. Always return "
                    "at least the primary domain even when needs_attention is not empty."
                ),
                input=self._generation_input(word, usage_clue),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "vocabulary_entry",
                        "schema": VOCABULARY_SCHEMA,
                        "strict": True,
                    }
                },
            )
            logger.info(
                "Vocabulary AI generation OpenAI request completed in %.2fs for word '%s'",
                time.perf_counter() - started_at,
                word,
            )
        except ImportError:
            logger.exception("Vocabulary AI generation failed: OpenAI package is not installed")
            return None, "OpenAI package is not installed. Run python -m pip install -r requirements.txt"
        except Exception as error:
            logger.exception(
                "Vocabulary AI generation failed during OpenAI request: %s",
                error.__class__.__name__,
            )
            return None, f"OpenAI request failed: {error.__class__.__name__}"

        try:
            entry = json.loads(response.output_text)
        except (AttributeError, json.JSONDecodeError):
            logger.exception("Vocabulary AI generation failed: invalid response format")
            return None, "OpenAI returned invalid vocabulary data"

        entry["word"] = word
        entry["context"] = self._normalize_context(entry.get("context"))
        entry["frequency_band"] = self._normalize_frequency_band(
            entry.get("frequency_band")
        )
        entry["frequency_note"] = self._normalize_frequency_note(
            entry.get("frequency_note")
        )
        entry["domains"] = self._normalize_domains(entry.get("domains"))
        entry["examples"] = self._normalize_examples(entry.get("examples"))
        entry["cloze_sentences"] = self._normalize_cloze_sentences(
            entry.get("cloze_sentences")
        )
        assessment_error = self._normalize_ai_assessment(entry)
        if len(entry["examples"]) < 2:
            logger.warning("Vocabulary AI generation failed: fewer than 2 examples returned")
            return None, "OpenAI returned invalid vocabulary data"
        if len(entry["domains"]) < 1:
            logger.warning("Vocabulary AI generation failed: no valid domains returned")
            return None, "OpenAI returned invalid vocabulary data"
        if not entry["frequency_band"]:
            logger.warning("Vocabulary AI generation failed: invalid frequency band")
            return None, "OpenAI returned invalid vocabulary data"
        if assessment_error:
            logger.warning("Vocabulary AI generation failed: invalid AI assessment")
            return None, "OpenAI returned invalid vocabulary data"
        if len(entry["cloze_sentences"]) < 2:
            logger.warning("Vocabulary AI generation failed: fewer than 2 cloze sentences returned")
            return None, "OpenAI returned invalid vocabulary data"
        logger.info("Vocabulary AI generation succeeded for word '%s'", word)
        return entry, None

    def generate_cloze_data(self, entry, api_key, model):
        if not api_key:
            logger.warning("Cloze AI generation failed: missing OpenAI API key")
            return None, "OpenAI API key is missing"

        word = entry["word"]
        logger.info("Cloze AI generation started for word '%s' using model '%s'", word, model)
        try:
            client = self._get_client(api_key)
            started_at = time.perf_counter()
            response = client.responses.create(
                model=model,
                max_output_tokens=CLOZE_DATA_MAX_OUTPUT_TOKENS,
                store=False,
                instructions=(
                    "Create missing cloze training data for one vocabulary entry. "
                    "Return JSON only. Identify the primary part of speech for the "
                    "given meaning using noun, verb, adjective, adverb, phrase, or other. "
                    "Assign 1-3 ordered semantic domains using only: "
                    f"{', '.join(VOCABULARY_DOMAINS)}. The first item is the primary "
                    "domain. Add secondary and tertiary domains only when clearly "
                    "represented by the meaning. Domains describe meaning and are "
                    "separate from usage context such as Academic or Medical. "
                    "Create 2-3 natural cloze sentences. Each sentence must include "
                    "exactly one ____ blank where the target word belongs, must not "
                    "include the target word elsewhere, and must fit the definition. "
                    "Return a confidence score from 0 to 100 for all generated data. "
                    "If admin review is needed, return a concise explanation of at most "
                    "200 characters in needs_attention; otherwise return an empty "
                    "string. Always return at least the primary domain even when "
                    "attention is needed."
                ),
                input=(
                    f"Word: {word}\n"
                    f"Definition: {entry['definition']}\n"
                    f"Context: {entry.get('context') or 'General'}\n"
                    f"Examples:\n"
                    + "\n".join(f"- {example}" for example in entry.get("examples", []))
                ),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "cloze_data",
                        "schema": CLOZE_DATA_SCHEMA,
                        "strict": True,
                    }
                },
            )
            logger.info(
                "Cloze AI generation OpenAI request completed in %.2fs for word '%s'",
                time.perf_counter() - started_at,
                word,
            )
        except ImportError:
            logger.exception("Cloze AI generation failed: OpenAI package is not installed")
            return None, "OpenAI package is not installed. Run python -m pip install -r requirements.txt"
        except Exception as error:
            logger.exception(
                "Cloze AI generation failed during OpenAI request: %s",
                error.__class__.__name__,
            )
            return None, f"OpenAI request failed: {error.__class__.__name__}"

        try:
            cloze_data = json.loads(response.output_text)
        except (AttributeError, json.JSONDecodeError):
            logger.exception("Cloze AI generation failed: invalid response format")
            return None, "OpenAI returned invalid cloze data"

        cloze_data["cloze_sentences"] = self._normalize_cloze_sentences(
            cloze_data.get("cloze_sentences")
        )
        cloze_data["domains"] = self._normalize_domains(cloze_data.get("domains"))
        assessment_error = self._normalize_ai_assessment(cloze_data)
        if len(cloze_data["cloze_sentences"]) < 2:
            return None, "OpenAI returned invalid cloze data"
        if len(cloze_data["domains"]) < 1:
            return None, "OpenAI returned invalid cloze data"
        if assessment_error:
            return None, "OpenAI returned invalid cloze data"
        logger.info("Cloze AI generation succeeded for word '%s'", word)
        return cloze_data, None

    def generate_synonym_net_cloze_data(self, entries, api_key, model):
        if not api_key:
            logger.warning("Synonym net cloze generation failed: missing OpenAI API key")
            return None, "OpenAI API key is missing"
        if len(entries) < 2:
            return None, "Synonym net must contain at least two entries"

        logger.info(
            "Synonym net cloze generation started for %s entries using model '%s'",
            len(entries),
            model,
        )
        try:
            client = self._get_client(api_key)
            started_at = time.perf_counter()
            response = client.responses.create(
                model=model,
                max_output_tokens=SYNONYM_NET_CLOZE_MAX_OUTPUT_TOKENS,
                store=False,
                instructions=(
                    "Create contrastive cloze training sentences for a graph of "
                    "linked near-synonyms. Return JSON only. For each vocabulary "
                    "entry, create 2-3 cloze sentences that clearly favor that "
                    "target word over the other words in the synonym graph. Each "
                    "sentence must include exactly one ____ blank where the target "
                    "word belongs, must not include the target word elsewhere, and "
                    "must be specific enough that a learner choosing among the graph "
                    "words can identify the correct word by semantic nuance. Avoid "
                    "generic sentences where several graph words fit equally well. "
                    "Respect each entry's part of speech, definition, context, "
                    "domains, and examples. Return one result for every input "
                    "vocabulary_id. Return a confidence score from 0 to 100 for "
                    "each entry. If an entry's contrastive distinction needs admin "
                    "review, put a concise explanation of at most 200 characters in "
                    "needs_attention; otherwise return an empty string."
                ),
                input=self._synonym_net_cloze_input(entries),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "synonym_net_cloze_data",
                        "schema": SYNONYM_NET_CLOZE_SCHEMA,
                        "strict": True,
                    }
                },
            )
            logger.info(
                "Synonym net cloze generation OpenAI request completed in %.2fs",
                time.perf_counter() - started_at,
            )
        except ImportError:
            logger.exception("Synonym net cloze generation failed: OpenAI package is not installed")
            return None, "OpenAI package is not installed. Run python -m pip install -r requirements.txt"
        except Exception as error:
            logger.exception(
                "Synonym net cloze generation failed during OpenAI request: %s",
                error.__class__.__name__,
            )
            return None, f"OpenAI request failed: {error.__class__.__name__}"

        try:
            data = json.loads(response.output_text)
        except (AttributeError, json.JSONDecodeError):
            logger.exception("Synonym net cloze generation failed: invalid response format")
            return None, "OpenAI returned invalid synonym net cloze data"

        results = []
        for item in data.get("entries", []):
            cloze_sentences = self._normalize_cloze_sentences(item.get("cloze_sentences"))
            normalized_item = {
                "vocabulary_id": item.get("vocabulary_id"),
                "cloze_sentences": cloze_sentences,
                "needs_attention": str(item.get("needs_attention") or "").strip() or None,
                "confidence_score": item.get("confidence_score"),
            }
            if (
                not isinstance(normalized_item["vocabulary_id"], int)
                or len(cloze_sentences) < 2
                or len(cloze_sentences) > 3
                or len(normalized_item["needs_attention"] or "") > 200
                or isinstance(normalized_item["confidence_score"], bool)
                or not isinstance(normalized_item["confidence_score"], int)
                or not 0 <= normalized_item["confidence_score"] <= 100
            ):
                return None, "OpenAI returned invalid synonym net cloze data"
            results.append(normalized_item)

        logger.info("Synonym net cloze generation succeeded")
        return {"entries": results}, None

    def validate_usage(self, entry, sentence, api_key, model):
        sentence = (sentence or "").strip()
        if not sentence:
            return None, "Sentence is required"
        if len(sentence) > 500:
            return None, "Sentence must be 500 characters or fewer"
        if not api_key:
            return None, "OpenAI API key is missing"

        word = entry["word"]
        logger.info("Vocabulary usage validation started for word '%s' using model '%s'", word, model)
        try:
            client = self._get_client(api_key)
            started_at = time.perf_counter()
            response = client.responses.create(
                model=model,
                max_output_tokens=USAGE_VALIDATION_MAX_OUTPUT_TOKENS,
                store=False,
                instructions=(
                    "Validate whether the learner uses the target vocabulary word correctly "
                    "in the submitted sentence. Focus on the meaning and usage of the target "
                    "word in context. Ignore minor grammar, spelling, capitalization, and typing "
                    "errors unless they prevent understanding. Return JSON only. Use result "
                    "'correct' or 'incorrect'. If incorrect, provide exactly one concise sentence "
                    "as a hint explaining how to improve the usage; if correct, hint must be empty."
                ),
                input=(
                    f"Target word: {word}\n"
                    f"Definition: {entry['definition']}\n"
                    f"Context: {entry.get('context') or 'General'}\n"
                    f"Example sentences:\n"
                    + "\n".join(f"- {example}" for example in entry.get("examples", []))
                    + f"\nLearner sentence: {sentence}"
                ),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "usage_validation",
                        "schema": USAGE_VALIDATION_SCHEMA,
                        "strict": True,
                    }
                },
            )
            logger.info(
                "Vocabulary usage validation OpenAI request completed in %.2fs for word '%s'",
                time.perf_counter() - started_at,
                word,
            )
        except ImportError:
            logger.exception("Vocabulary usage validation failed: OpenAI package is not installed")
            return None, "OpenAI package is not installed. Run python -m pip install -r requirements.txt"
        except Exception as error:
            logger.exception(
                "Vocabulary usage validation failed during OpenAI request: %s",
                error.__class__.__name__,
            )
            return None, f"OpenAI request failed: {error.__class__.__name__}"

        try:
            result = json.loads(response.output_text)
        except (AttributeError, json.JSONDecodeError):
            logger.exception("Vocabulary usage validation failed: invalid response format")
            return None, "OpenAI returned invalid usage validation data"

        if result.get("result") not in {"correct", "incorrect"}:
            return None, "OpenAI returned invalid usage validation data"
        hint = (result.get("hint") or "").strip()
        if result["result"] == "correct":
            hint = ""
        elif not hint:
            hint = "Try using the word in a sentence that matches its definition."

        logger.info("Vocabulary usage validation succeeded for word '%s'", word)
        return {"result": result["result"], "hint": hint}, None

    def validate_word(self, word):
        return self._validate_word(word)

    def _validate_word(self, word):
        word = (word or "").strip()
        if not WORD_PATTERN.fullmatch(word):
            return None, "Please provide one word only"
        return word, None

    def _validate_usage_clue(self, usage_clue, word):
        usage_clue = (usage_clue or "").strip()
        if not usage_clue:
            return "", None
        if len(usage_clue) > MAX_USAGE_CLUE_LENGTH:
            return None, f"Usage clue must be {MAX_USAGE_CLUE_LENGTH} characters or fewer"
        if re.search(r"<[^>]+>", usage_clue):
            return None, "HTML tags are not allowed"

        marked_words = re.findall(r"\(([^()]+)\)", usage_clue)
        if marked_words:
            normalized_word = word.lower()
            for marked_word in marked_words:
                candidate = marked_word.strip().strip(".,;:!?\"'").lower()
                if candidate != normalized_word:
                    return None, "Usage clue parentheses must mark the target word"
        return usage_clue, None

    def _generation_input(self, word, usage_clue):
        lines = [f"Word: {word}"]
        if usage_clue:
            lines.append(f"Usage clue: {usage_clue}")
        return "\n".join(lines)

    def _synonym_net_cloze_input(self, entries):
        lines = ["Synonym graph entries:"]
        for entry in entries:
            lines.extend(
                [
                    f"Vocabulary ID: {entry['id']}",
                    f"Word: {entry['word']}",
                    f"Part of speech: {entry.get('part_of_speech') or 'other'}",
                    f"Definition: {entry['definition']}",
                    f"Context: {entry.get('context') or 'General'}",
                    f"Frequency: {entry.get('frequency_band') or 'unknown'}",
                    "Domains: " + ", ".join(entry.get("domains", []) or ["none"]),
                    "Examples:",
                ]
            )
            lines.extend(f"- {example}" for example in entry.get("examples", []))
            lines.append("")
        return "\n".join(lines)

    def _normalize_context(self, context):
        context = (context or "").strip()
        labels = [
            " ".join(label.strip().split())
            for label in context.split("/")
            if label.strip()
        ]
        if (
            1 <= len(labels) <= 4
            and all(label in ALLOWED_CONTEXT_LABELS for label in labels)
        ):
            return "/".join(labels)
        logger.info("Vocabulary AI generation replaced sentence-like context with General")
        return "General"

    def _normalize_frequency_band(self, frequency_band):
        frequency_band = (
            str(frequency_band or "")
            .strip()
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
        )
        if frequency_band in FREQUENCY_BANDS:
            return frequency_band
        return None

    def _normalize_frequency_note(self, frequency_note):
        return str(frequency_note or "").strip()[:300]

    def _normalize_examples(self, examples):
        if not isinstance(examples, list):
            return []
        return [
            str(example).strip()
            for example in examples
            if str(example).strip()
        ][:4]

    def _normalize_domains(self, domains):
        if not isinstance(domains, list):
            return []

        normalized_domains = []
        for domain in domains:
            normalized_domain = str(domain).strip().lower()
            if (
                normalized_domain in VOCABULARY_DOMAINS
                and normalized_domain not in normalized_domains
            ):
                normalized_domains.append(normalized_domain)
        return normalized_domains[:MAX_AI_VOCABULARY_DOMAINS]

    def _normalize_ai_assessment(self, data):
        needs_attention = str(data.get("needs_attention") or "").strip()
        confidence_score = data.get("confidence_score")
        if (
            len(needs_attention) > 200
            or isinstance(confidence_score, bool)
            or not isinstance(confidence_score, int)
            or not 0 <= confidence_score <= 100
        ):
            return True

        data["needs_attention"] = needs_attention or None
        data["confidence_score"] = confidence_score
        return False

    def _normalize_cloze_sentences(self, cloze_sentences):
        if not isinstance(cloze_sentences, list):
            return []
        return [
            str(sentence).strip()
            for sentence in cloze_sentences
            if str(sentence).strip()
        ][:3]

    def _get_client(self, api_key):
        if self._client is not None:
            return self._client

        from openai import OpenAI

        return OpenAI(
            api_key=api_key,
            max_retries=OPENAI_MAX_RETRIES,
            timeout=OPENAI_REQUEST_TIMEOUT_SECONDS,
        )


vocabulary_ai_service = VocabularyAiService()
