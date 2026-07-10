from flask import current_app, has_app_context

from Repositories.vocabulary_repository import (
    vocabulary_repository as default_vocabulary_repository,
)
from Services.background_job_service import (
    background_job_service as default_background_job_service,
)


class VocabularySynonymLinkService:
    def __init__(
        self,
        vocabulary_repository=default_vocabulary_repository,
        background_job_service=default_background_job_service,
    ):
        self._vocabulary_repository = vocabulary_repository
        self._background_job_service = background_job_service

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
                link_changed = synonym_row["linked_vocabulary_id"] != target["id"]
                self._vocabulary_repository.link_synonym(
                    synonym_row["id"],
                    target["id"],
                )
                self._vocabulary_repository.ensure_synonym(
                    target["id"],
                    entry["word"],
                    vocabulary_id,
                )
                if link_changed:
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
                link_changed = incoming_row["linked_vocabulary_id"] != vocabulary_id
                self._vocabulary_repository.link_synonym(incoming_row["id"], vocabulary_id)
                source_entry = self._vocabulary_repository.get_entry(incoming_row["vocabulary_id"])
                if source_entry:
                    self._vocabulary_repository.ensure_synonym(
                        vocabulary_id,
                        source_entry["word"],
                        source_entry["id"],
                    )
                if link_changed:
                    linked_count += 1
        elif incoming_rows:
            ambiguous_count += len(incoming_rows)

        if linked_count and self._synonym_net_cloze_jobs_enabled():
            self._background_job_service.enqueue_synonym_net_cloze_generation(vocabulary_id)

        return {"linked": linked_count, "ambiguous": ambiguous_count}

    def repair_all_vocabulary_synonyms(self):
        summary = {"entries": 0, "linked": 0, "ambiguous": 0}
        for vocabulary_id in self._vocabulary_repository.list_entry_ids():
            result = self.link_vocabulary_synonyms(vocabulary_id)
            summary["entries"] += 1
            summary["linked"] += result["linked"]
            summary["ambiguous"] += result["ambiguous"]
        return summary

    def _synonym_net_cloze_jobs_enabled(self):
        if not has_app_context():
            return True
        return current_app.config.get("SYNONYM_NET_CLOZE_JOBS_ENABLED", True)


vocabulary_synonym_link_service = VocabularySynonymLinkService()
