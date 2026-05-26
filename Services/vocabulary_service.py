import re

from Repositories.vocabulary_repository import (
    vocabulary_repository as default_vocabulary_repository,
)


HTML_PATTERN = re.compile(r"<[^>]+>")
SQL_INJECTION_PATTERN = re.compile(
    r"(--|/\*|\*/|\bOR\b\s+\d+\s*=\s*\d+|\bDROP\b|\bDELETE\b|\bINSERT\b|\bUPDATE\b|\bUNION\b|\bSELECT\b)",
    re.IGNORECASE,
)
SEARCH_PATTERN = re.compile(r"^[A-Za-z*]+$")


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
            values["synonyms"],
            values["examples"],
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
            values["synonyms"],
            values["examples"],
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

    def validate_entry_data(self, data):
        return self._validate_data(data)

    def _validate_data(self, data):
        word = self._clean_text(data.get("word"))
        definition = self._clean_text(data.get("definition"))
        context = self._clean_text(data.get("context"))
        synonyms = self._clean_list(data.get("synonyms", []))
        examples = self._clean_list(data.get("examples", []))

        fields = [word, definition, context] + synonyms + examples
        unsafe_field = self._find_unsafe_field(fields)
        if unsafe_field:
            return None, "HTML tags and SQL statements are not allowed"

        if not word:
            return None, "Word is required"
        if not definition:
            return None, "Definition is required"
        if len(examples) < 1 or len(examples) > 4:
            return None, "Vocabulary entry must have 1-4 example sentences"

        return {
            "word": word,
            "definition": definition,
            "context": context,
            "synonyms": synonyms,
            "examples": examples,
        }, None

    def _clean_text(self, value):
        if value is None:
            return ""
        return str(value).strip()

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

    def _find_unsafe_field(self, values):
        for value in values:
            if HTML_PATTERN.search(value) or SQL_INJECTION_PATTERN.search(value):
                return value
        return None

    def _validate_search_value(self, search_value):
        if not search_value:
            return "Search word is required"
        if HTML_PATTERN.search(search_value) or SQL_INJECTION_PATTERN.search(search_value):
            return "HTML tags and SQL statements are not allowed"
        if not SEARCH_PATTERN.fullmatch(search_value):
            return "Search may only contain letters and wildcard *"
        return None


vocabulary_service = VocabularyService()
