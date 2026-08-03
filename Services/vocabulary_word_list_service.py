from pathlib import Path

from Repositories.vocabulary_repository import vocabulary_repository


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUILT_IN_WORD_LISTS = (
    {
        "key": "gregmat",
        "name": "GregMat",
        "category": "GRE",
        "source_url": (
            "https://docs.google.com/spreadsheets/d/"
            "1jRATLVV34vATsL4Y67fZZXQc7qZPYc0c0Yk7Bykh4fw/edit"
        ),
        "words_path": _PROJECT_ROOT / "Resources" / "gregmat_gre_words.txt",
    },
)


class VocabularyWordListService:
    def __init__(self, repository=vocabulary_repository):
        self._repository = repository

    def sync_builtin_word_lists(self):
        summaries = []
        for word_list in BUILT_IN_WORD_LISTS:
            words = self._words_from_file(word_list["words_path"])
            word_list_id = self._repository.ensure_word_list(
                word_list["key"],
                word_list["name"],
                word_list["category"],
                word_list["source_url"],
            )
            self._repository.replace_word_list_entries(word_list_id, words)
            matched_entries = self._repository.sync_word_list_memberships(word_list_id)
            summaries.append(
                {
                    "key": word_list["key"],
                    "name": word_list["name"],
                    "word_count": len(words),
                    "matched_entries": matched_entries,
                }
            )
        return summaries

    @staticmethod
    def _words_from_file(words_path):
        words = []
        seen_words = set()
        for raw_word in words_path.read_text(encoding="utf-8").splitlines():
            word = raw_word.strip()
            key = word.casefold()
            if not word or word.startswith("#") or key in seen_words:
                continue
            words.append(word)
            seen_words.add(key)
        return words


vocabulary_word_list_service = VocabularyWordListService()
