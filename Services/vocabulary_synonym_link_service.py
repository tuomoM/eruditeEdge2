from Repositories.vocabulary_repository import (
    vocabulary_repository as default_vocabulary_repository,
)


class VocabularySynonymLinkService:
    def __init__(self, vocabulary_repository=default_vocabulary_repository):
        self._vocabulary_repository = vocabulary_repository

    def link_vocabulary_synonyms(self, vocabulary_id):
        entry = self._vocabulary_repository.get_entry(vocabulary_id)
        if not entry:
            return {"linked": 0, "ambiguous": 0}

        linked_count = 0
        ambiguous_count = 0
        synonym_rows = self._vocabulary_repository.list_synonym_rows(vocabulary_id)
        for synonym_row in synonym_rows:
            matches = self._vocabulary_repository.find_entries_by_word(
                synonym_row["synonym"],
                exclude_vocabulary_id=vocabulary_id,
            )
            if len(matches) == 1:
                target = matches[0]
                self._vocabulary_repository.link_synonym(
                    synonym_row["id"],
                    target["id"],
                )
                self._vocabulary_repository.ensure_synonym(
                    target["id"],
                    entry["word"],
                    vocabulary_id,
                )
                linked_count += 1
            else:
                self._vocabulary_repository.link_synonym(synonym_row["id"], None)
                if len(matches) > 1:
                    ambiguous_count += 1

        incoming_rows = self._vocabulary_repository.find_synonym_rows_by_text(
            entry["word"],
            exclude_vocabulary_id=vocabulary_id,
        )
        word_matches = self._vocabulary_repository.find_entries_by_word(entry["word"])
        if len(word_matches) == 1:
            for incoming_row in incoming_rows:
                self._vocabulary_repository.link_synonym(incoming_row["id"], vocabulary_id)
                source_entry = self._vocabulary_repository.get_entry(incoming_row["vocabulary_id"])
                if source_entry:
                    self._vocabulary_repository.ensure_synonym(
                        vocabulary_id,
                        source_entry["word"],
                        source_entry["id"],
                    )
                    linked_count += 1
        elif incoming_rows:
            ambiguous_count += len(incoming_rows)

        return {"linked": linked_count, "ambiguous": ambiguous_count}


vocabulary_synonym_link_service = VocabularySynonymLinkService()
