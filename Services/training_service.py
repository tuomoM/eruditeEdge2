from Repositories.training_repository import training_repository as default_training_repository
from Repositories.vocabulary_repository import (
    vocabulary_repository as default_vocabulary_repository,
)


class TrainingService:
    def __init__(
        self,
        training_repository=default_training_repository,
        vocabulary_repository=default_vocabulary_repository,
    ):
        self._training_repository = training_repository
        self._vocabulary_repository = vocabulary_repository

    def create_training_session(self, user_id, vocabulary_ids):
        vocabulary_ids, error = self._clean_vocabulary_ids(vocabulary_ids)
        if error:
            return None, error

        missing_ids = [
            vocabulary_id
            for vocabulary_id in vocabulary_ids
            if self._vocabulary_repository.get_entry(vocabulary_id) is None
        ]
        if missing_ids:
            return None, "Selected vocabulary contains unknown entries"

        training_session_id = self._training_repository.create_training_session(
            user_id,
            vocabulary_ids,
        )
        return self.get_training_session(training_session_id, user_id), None

    def get_training_session(self, training_session_id, user_id):
        training_session = self._training_repository.get_training_session(
            training_session_id,
            user_id,
        )
        if not training_session:
            return None

        training_session["vocabs"] = [
            self._vocabulary_repository.get_entry(vocabulary_id)
            for vocabulary_id in training_session["vocabulary_ids"]
        ]
        return training_session

    def _clean_vocabulary_ids(self, vocabulary_ids):
        if not vocabulary_ids:
            return None, "Choose at least one vocabulary entry"

        cleaned_ids = []
        seen_ids = set()
        for vocabulary_id in vocabulary_ids:
            try:
                cleaned_id = int(vocabulary_id)
            except (TypeError, ValueError):
                return None, "Invalid vocabulary selection"

            if cleaned_id <= 0:
                return None, "Invalid vocabulary selection"
            if cleaned_id not in seen_ids:
                cleaned_ids.append(cleaned_id)
                seen_ids.add(cleaned_id)

        return cleaned_ids, None


training_service = TrainingService()
