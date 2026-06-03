import json
import logging
import re


logger = logging.getLogger(__name__)
WORD_PATTERN = re.compile(r"^[A-Za-z]+(?:[-'][A-Za-z]+)?$")
ALLOWED_CONTEXT_LABELS = {
    "Academic",
    "Business",
    "Business English",
    "Casual",
    "Education",
    "Emotional",
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
    "Political",
    "Professional",
    "Religious",
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
                "A short usage category or register, not an example sentence. "
                "Use 1-4 slash-separated labels such as Formal, Casual, "
                "Medical, Philosophy, Academic, Business English, Business/Formal."
            ),
        },
        "synonyms": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 0,
            "maxItems": 8,
        },
        "examples": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 4,
        },
    },
    "required": ["word", "definition", "context", "synonyms", "examples"],
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


class VocabularyAiService:
    def __init__(self, client=None):
        self._client = client

    def generate_entry(self, word, api_key, model):
        word, error = self._validate_word(word)
        if error:
            logger.info("Vocabulary AI generation rejected input: %s", error)
            return None, error
        if not api_key:
            logger.warning("Vocabulary AI generation failed: missing OpenAI API key")
            return None, "OpenAI API key is missing"

        logger.info("Vocabulary AI generation started for word '%s' using model '%s'", word, model)
        try:
            client = self._get_client(api_key)
            response = client.responses.create(
                model=model,
                instructions=(
                    "Create vocabulary entry data for the provided single word. "
                    "Return only factual dictionary-style data. Do not include HTML. "
                    "The context field must be a short usage category/register/domain, "
                    "not a sentence. Examples: Formal, Casual, Medical, Philosophy, "
                    "Academic, Business English, Business/Formal."
                ),
                input=f"Word: {word}",
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "vocabulary_entry",
                        "schema": VOCABULARY_SCHEMA,
                        "strict": True,
                    }
                },
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
        logger.info("Vocabulary AI generation succeeded for word '%s'", word)
        return entry, None

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
            response = client.responses.create(
                model=model,
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

    def _get_client(self, api_key):
        if self._client is not None:
            return self._client

        from openai import OpenAI

        return OpenAI(api_key=api_key)


vocabulary_ai_service = VocabularyAiService()
