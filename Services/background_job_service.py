from Repositories.background_job_repository import (
    background_job_repository as default_background_job_repository,
)


LINK_VOCABULARY_SYNONYMS_JOB = "link_vocabulary_synonyms"


class BackgroundJobService:
    def __init__(
        self,
        background_job_repository=default_background_job_repository,
        handlers=None,
    ):
        self._background_job_repository = background_job_repository
        self._handlers = handlers or {}

    def register_handler(self, job_type, handler):
        self._handlers[job_type] = handler

    def enqueue_vocabulary_synonym_linking(self, vocabulary_id):
        return self._background_job_repository.enqueue(
            LINK_VOCABULARY_SYNONYMS_JOB,
            {"vocabulary_id": vocabulary_id},
        )

    def run_pending(self, limit=10):
        summary = {"processed": 0, "completed": 0, "failed": 0}
        for job in self._background_job_repository.list_pending(limit):
            if not self._background_job_repository.mark_running(job["id"]):
                continue
            summary["processed"] += 1
            try:
                self._handle_job(job)
            except Exception as error:
                self._background_job_repository.mark_failed(job["id"], error)
                summary["failed"] += 1
                continue
            self._background_job_repository.delete(job["id"])
            summary["completed"] += 1
        return summary

    def _handle_job(self, job):
        handler = self._handlers.get(job["job_type"])
        if handler is None:
            raise ValueError(f"Unknown background job type: {job['job_type']}")
        handler(job["payload"])


background_job_service = BackgroundJobService()
