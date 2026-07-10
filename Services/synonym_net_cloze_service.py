from Repositories.vocabulary_repository import (
    vocabulary_repository as default_vocabulary_repository,
)
from Services.vocabulary_ai_service import vocabulary_ai_service as default_vocabulary_ai_service
from Services.vocabulary_service import vocabulary_service as default_vocabulary_service


MAX_SYNONYM_NET_SIZE = 12


class SynonymNetClozeService:
    def __init__(
        self,
        vocabulary_repository=default_vocabulary_repository,
        vocabulary_ai_service=default_vocabulary_ai_service,
        vocabulary_service=default_vocabulary_service,
    ):
        self._vocabulary_repository = vocabulary_repository
        self._vocabulary_ai_service = vocabulary_ai_service
        self._vocabulary_service = vocabulary_service

    def synonym_net_entries(self, vocabulary_id):
        visited = set()
        queue = [vocabulary_id]
        while queue and len(visited) < MAX_SYNONYM_NET_SIZE:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            entry = self._vocabulary_repository.get_entry(current_id)
            if not entry:
                continue
            visited.add(current_id)
            for linked_id in self._vocabulary_repository.list_linked_synonym_vocabulary_ids(
                current_id
            ):
                if linked_id not in visited and linked_id not in queue:
                    queue.append(linked_id)

        entries = []
        for entry_id in sorted(visited):
            entry = self._vocabulary_repository.get_entry(entry_id)
            if entry:
                entries.append(entry)
        return entries

    def generate_for_vocabulary(self, vocabulary_id, api_key, model):
        entries = self.synonym_net_entries(vocabulary_id)
        if len(entries) < 2:
            return {"updated": 0, "skipped": "Synonym net has fewer than two entries"}, None

        generated_data, error = self._vocabulary_ai_service.generate_synonym_net_cloze_data(
            entries,
            api_key,
            model,
        )
        if error:
            return None, error

        updates, error = self._validated_updates(entries, generated_data)
        if error:
            return None, error

        for entry, update in updates:
            updated_entry, error = self._vocabulary_service.update_ai_maintenance_data(
                entry["id"],
                update,
            )
            if error:
                return None, error

        return {"updated": len(updates), "skipped": None}, None

    def _validated_updates(self, entries, generated_data):
        entries_by_id = {entry["id"]: entry for entry in entries}
        generated_items = generated_data.get("entries", [])
        generated_by_id = {item.get("vocabulary_id"): item for item in generated_items}
        if set(generated_by_id) != set(entries_by_id):
            return None, "OpenAI returned incomplete synonym net cloze data"

        updates = []
        for vocabulary_id, entry in entries_by_id.items():
            item = generated_by_id[vocabulary_id]
            update = {
                "part_of_speech": entry["part_of_speech"],
                "domains": entry["domains"],
                "cloze_sentences": item["cloze_sentences"],
                "needs_attention": item.get("needs_attention"),
                "confidence_score": item.get("confidence_score"),
            }
            _, error = self._vocabulary_service.validate_ai_maintenance_data(
                entry,
                update,
            )
            if error:
                return None, error
            updates.append((entry, update))
        return updates, None


synonym_net_cloze_service = SynonymNetClozeService()
