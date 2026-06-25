import re

from Repositories.vocabulary_repository import (
    vocabulary_repository as default_vocabulary_repository,
)
from Services.vocabulary_domains import MAX_VOCABULARY_DOMAINS, VOCABULARY_DOMAINS


HTML_PATTERN = re.compile(r"<[^>]+>")
SQL_INJECTION_PATTERN = re.compile(
    r"(--|/\*|\*/|\bOR\b\s+\d+\s*=\s*\d+|\bDROP\b|\bDELETE\b|\bINSERT\b|\bUPDATE\b|\bUNION\b|\bSELECT\b)",
    re.IGNORECASE,
)
SEARCH_PATTERN = re.compile(r"^[A-Za-z*]+$")
ALLOWED_PARTS_OF_SPEECH = {
    "noun",
    "verb",
    "adjective",
    "adverb",
    "phrase",
    "other",
}
CLOZE_BLANK = "____"
MAX_NEEDS_ATTENTION_LENGTH = 200


class VocabularyService:
    def __init__(self, vocabulary_repository=default_vocabulary_repository):
        self._vocabulary_repository = vocabulary_repository

    def create_entry(self, data, user_id):
        values, error = self._validate_data(data)
        if error:
            return None, error

        vocabulary_id = self._vocabulary_repository.create_entry(
            values["word"],
            values["definition"],
            values["context"],
            values["part_of_speech"],
            values["domains"],
            values["synonyms"],
            values["examples"],
            values["cloze_sentences"],
            values["needs_attention"],
            values["confidence_score"],
            user_id,
        )
        if vocabulary_id is None:
            return None, "Vocabulary entry already exists for this word and context"
        return self._vocabulary_repository.get_entry(vocabulary_id), None

    def update_entry(self, vocabulary_id, data):
        values, error = self._validate_data(data)
        if error:
            return None, error

        updated = self._vocabulary_repository.update_entry(
            vocabulary_id,
            values["word"],
            values["definition"],
            values["context"],
            values["part_of_speech"],
            values["domains"],
            values["synonyms"],
            values["examples"],
            values["cloze_sentences"],
        )
        if not updated:
            return None, "Vocabulary entry was not found or already exists"
        return self._vocabulary_repository.get_entry(vocabulary_id), None

    def get_entry(self, vocabulary_id):
        return self._vocabulary_repository.get_entry(vocabulary_id)

    def search_by_word(self, search_value):
        search_value = self._clean_text(search_value)
        error = self._validate_search_value(search_value)
        if error:
            return None, error

        search_term = search_value.replace("*", "%")
        return self._vocabulary_repository.search_by_word(search_term), None

    def list_entries(self):
        return self._vocabulary_repository.list_entries()

    def count_entries_created_since(self, created_since):
        return self._vocabulary_repository.count_created_since(created_since)

    def delete_entries_by_user(self, user_id):
        return self._vocabulary_repository.delete_entries_by_user(user_id)

    def validate_entry_data(self, data):
        return self._validate_data(data)

    def list_cloze_maintenance_entries(self):
        entries = self._vocabulary_repository.list_entries()
        return [
            entry
            for entry in entries
            if (
                entry["part_of_speech"] == "other"
                or not entry["domains"]
                or len(entry["cloze_sentences"]) < 2
                or bool(entry["needs_attention"])
                or entry["confidence_score"] is None
                or bool(entry["confidence_obsolete"])
                or self._validate_cloze_sentences(entry["word"], entry["cloze_sentences"])
            )
        ]

    def update_cloze_data(self, vocabulary_id, data):
        entry = self.get_entry(vocabulary_id)
        if not entry:
            return None, "Vocabulary entry was not found"

        merged_data = dict(entry)
        merged_data["part_of_speech"] = data.get("part_of_speech")
        merged_data["domains"] = data.get("domains", entry["domains"])
        merged_data["cloze_sentences"] = data.get("cloze_sentences", [])
        values, error = self._validate_data(merged_data)
        if error:
            return None, error

        updated = self._vocabulary_repository.update_cloze_data(
            vocabulary_id,
            values["part_of_speech"],
            values["cloze_sentences"],
            values["domains"],
        )
        if not updated:
            return None, "Vocabulary entry was not found"
        return self.get_entry(vocabulary_id), None

    def update_ai_maintenance_data(self, vocabulary_id, data):
        entry = self.get_entry(vocabulary_id)
        if not entry:
            return None, "Vocabulary entry was not found"

        merged_data = dict(entry)
        merged_data.update(data)
        values, error = self._validate_data(merged_data)
        if error:
            return None, error
        if values["confidence_score"] is None:
            return None, "AI confidence score is required"

        updated = self._vocabulary_repository.update_ai_maintenance_data(
            vocabulary_id,
            values["part_of_speech"],
            values["cloze_sentences"],
            values["domains"],
            values["needs_attention"],
            values["confidence_score"],
        )
        if not updated:
            return None, "Vocabulary entry was not found"
        return self.get_entry(vocabulary_id), None

    def _validate_data(self, data):
        word = self._clean_text(data.get("word"))
        definition = self._clean_text(data.get("definition"))
        context = self._clean_text(data.get("context"))
        part_of_speech = self._clean_part_of_speech(data.get("part_of_speech"))
        domains = self._clean_list(data.get("domains", []))
        synonyms = self._clean_list(data.get("synonyms", []))
        examples = self._clean_list(data.get("examples", []))
        cloze_sentences = self._clean_list(data.get("cloze_sentences", []))
        needs_attention = self._clean_optional_text(data.get("needs_attention"))
        confidence_score = self._clean_confidence_score(data.get("confidence_score"))

        fields = (
            [word, definition, context, part_of_speech]
            + domains
            + synonyms
            + examples
            + cloze_sentences
            + ([needs_attention] if needs_attention else [])
        )
        unsafe_field = self._find_unsafe_field(fields)
        if unsafe_field:
            return None, "HTML tags are not allowed"

        if not word:
            return None, "Word is required"
        if not definition:
            return None, "Definition is required"
        if part_of_speech not in ALLOWED_PARTS_OF_SPEECH:
            return None, "Part of speech is invalid"
        if len(domains) > MAX_VOCABULARY_DOMAINS:
            return None, f"Vocabulary entry must have at most {MAX_VOCABULARY_DOMAINS} domains"
        if any(domain not in VOCABULARY_DOMAINS for domain in domains):
            return None, "Vocabulary domain is invalid"
        if len(needs_attention or "") > MAX_NEEDS_ATTENTION_LENGTH:
            return None, (
                f"Needs-attention explanation must be "
                f"{MAX_NEEDS_ATTENTION_LENGTH} characters or fewer"
            )
        if confidence_score is False:
            return None, "Confidence score must be an integer between 0 and 100"
        if confidence_score is not None and not 0 <= confidence_score <= 100:
            return None, "Confidence score must be an integer between 0 and 100"
        if needs_attention and confidence_score is None:
            return None, "Confidence score is required when attention is needed"
        if len(examples) < 1 or len(examples) > 4:
            return None, "Vocabulary entry must have 1-4 example sentences"
        if len(cloze_sentences) > 3:
            return None, "Vocabulary entry must have at most 3 cloze sentences"
        cloze_error = self._validate_cloze_sentences(word, cloze_sentences)
        if cloze_error:
            return None, cloze_error

        return {
            "word": word,
            "definition": definition,
            "context": context,
            "part_of_speech": part_of_speech,
            "domains": domains,
            "synonyms": synonyms,
            "examples": examples,
            "cloze_sentences": cloze_sentences,
            "needs_attention": needs_attention,
            "confidence_score": confidence_score,
        }, None

    def _clean_text(self, value):
        if value is None:
            return ""
        return str(value).strip()

    def _clean_optional_text(self, value):
        value = self._clean_text(value)
        return value or None

    def _clean_confidence_score(self, value):
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return False

    def _clean_list(self, values):
        if isinstance(values, str):
            values = [values]
        if values is None:
            return []

        cleaned_values = []
        seen_values = set()
        for value in values:
            cleaned_value = self._clean_text(value)
            if cleaned_value and cleaned_value.lower() not in seen_values:
                cleaned_values.append(cleaned_value)
                seen_values.add(cleaned_value.lower())
        return cleaned_values

    def _clean_part_of_speech(self, value):
        value = self._clean_text(value).lower().replace(" ", "_")
        return value or "other"

    def _validate_cloze_sentences(self, word, cloze_sentences):
        word_pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
        for sentence in cloze_sentences:
            if sentence.count(CLOZE_BLANK) != 1:
                return "Each cloze sentence must contain exactly one ____ blank"
            if len(sentence) > 220:
                return "Cloze sentences must be 220 characters or fewer"
            if word_pattern.search(sentence):
                return "Cloze sentences must use ____ instead of the target word"
        return None

    def _find_unsafe_field(self, values):
        for value in values:
            if HTML_PATTERN.search(value):
                return value
        return None

    def _validate_search_value(self, search_value):
        if not search_value:
            return "Search word is required"
        if HTML_PATTERN.search(search_value):
            return "HTML tags are not allowed"
        if not SEARCH_PATTERN.fullmatch(search_value):
            return "Search may only contain letters and wildcard *"
        return None


vocabulary_service = VocabularyService()
