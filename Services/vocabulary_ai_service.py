import json
import re


WORD_PATTERN = re.compile(r"^[A-Za-z]+(?:[-'][A-Za-z]+)?$")
SQL_KEYWORD_PATTERN = re.compile(
    r"^(DROP|DELETE|INSERT|UPDATE|UNION|SELECT|ALTER|CREATE)$",
    re.IGNORECASE,
)


VOCABULARY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "word": {"type": "string"},
        "definition": {"type": "string"},
        "context": {"type": "string"},
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


class VocabularyAiService:
    def __init__(self, client=None):
        self._client = client

    def generate_entry(self, word, api_key, model):
        word, error = self._validate_word(word)
        if error:
            return None, error
        if not api_key:
            return None, "OpenAI API key is missing"

        client = self._get_client(api_key)
        response = client.responses.create(
            model=model,
            instructions=(
                "Create vocabulary entry data for the provided single word. "
                "Return only factual dictionary-style data. Do not include HTML."
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

        try:
            entry = json.loads(response.output_text)
        except (AttributeError, json.JSONDecodeError):
            return None, "OpenAI returned invalid vocabulary data"

        entry["word"] = word
        return entry, None

    def _validate_word(self, word):
        word = (word or "").strip()
        if not WORD_PATTERN.fullmatch(word) or SQL_KEYWORD_PATTERN.fullmatch(word):
            return None, "Please provide one word only"
        return word, None

    def _get_client(self, api_key):
        if self._client is not None:
            return self._client

        from openai import OpenAI

        return OpenAI(api_key=api_key)


vocabulary_ai_service = VocabularyAiService()
