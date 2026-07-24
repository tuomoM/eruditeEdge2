import hashlib

from Repositories.vocabulary_maintenance_repository import (
    vocabulary_maintenance_repository as default_vocabulary_maintenance_repository,
)
from Services.vocabulary_contexts import normalize_context_string
from Services.vocabulary_contexts import VOCABULARY_CONTEXTS
from Services.vocabulary_domains import active_vocabulary_domains
from Services.vocabulary_ai_service import (
    vocabulary_ai_service as default_vocabulary_ai_service,
)
from Services.vocabulary_maintenance_taxonomy import (
    DOMAIN_MODEL_PROMPT_TEMPLATE_VERSION,
    PROMPT_TEMPLATE_VERSION,
    RESPONSE_SCHEMA_VERSION,
    VALIDATOR_VERSION,
    domain_model_prompt_template_hash,
    frequency_rubric_snapshot,
    prompt_template_hash,
    stable_json,
    taxonomy_snapshot,
)
from Services.vocabulary_service import ALLOWED_FREQUENCY_BANDS


MAINTENANCE_ESTIMATED_INPUT_TOKENS_PER_ITEM = 900
MAINTENANCE_ESTIMATED_OUTPUT_TOKENS_PER_ITEM = 350
DOMAIN_MODEL_ESTIMATED_INPUT_TOKENS_PER_ITEM = 450
DOMAIN_MODEL_AGGREGATED_BASE_INPUT_TOKENS = 4000
DOMAIN_MODEL_AGGREGATED_MAX_INPUT_TOKENS = 22000
DOMAIN_MODEL_ESTIMATED_OUTPUT_TOKENS = 12000
MAINTENANCE_ESTIMATED_COST_PER_1K_TOKENS = 0.01
MAINTENANCE_SCOPES = {
    "all",
    "missing-domains",
    "domain",
    "context",
    "frequency-band",
    "created-after",
    "ids",
    "source",
}


class VocabularyMaintenanceService:
    def __init__(
        self,
        vocabulary_maintenance_repository=default_vocabulary_maintenance_repository,
        vocabulary_ai_service=default_vocabulary_ai_service,
    ):
        self._vocabulary_maintenance_repository = vocabulary_maintenance_repository
        self._vocabulary_ai_service = vocabulary_ai_service

    def prepare_run(
        self,
        name,
        scope,
        ai_model,
        max_items=None,
        max_estimated_cost=None,
        domain=None,
        context=None,
        frequency_band=None,
        created_after=None,
        ids=None,
        source_name=None,
        source_author=None,
        created_by=None,
    ):
        run_options, error = self._clean_run_options(
            name=name,
            scope=scope,
            ai_model=ai_model,
            max_items=max_items,
            max_estimated_cost=max_estimated_cost,
            domain=domain,
            context=context,
            frequency_band=frequency_band,
            created_after=created_after,
            ids=ids,
            source_name=source_name,
            source_author=source_author,
            created_by=created_by,
        )
        if error:
            return None, error

        item_snapshots = self._vocabulary_maintenance_repository.selected_entry_snapshots(
            run_options["filters"],
            run_options["max_items"],
        )
        for snapshot in item_snapshots:
            snapshot["source_snapshot_hash"] = hashlib.sha256(
                snapshot["source_snapshot_json"].encode("utf-8")
            ).hexdigest()

        selected_count = len(item_snapshots)
        estimated_input_tokens = selected_count * MAINTENANCE_ESTIMATED_INPUT_TOKENS_PER_ITEM
        estimated_output_tokens = selected_count * MAINTENANCE_ESTIMATED_OUTPUT_TOKENS_PER_ITEM
        estimated_cost = self._estimate_cost(
            estimated_input_tokens,
            estimated_output_tokens,
        )
        if (
            run_options["max_estimated_cost"] is not None
            and estimated_cost > run_options["max_estimated_cost"]
        ):
            return None, (
                f"Estimated cost {estimated_cost:.2f} exceeds max "
                f"{run_options['max_estimated_cost']:.2f}"
            )

        run_data = {
            "name": run_options["name"],
            "selection_filter_json": stable_json(run_options["selection_filter"]),
            "selected_count": selected_count,
            "taxonomy_snapshot_json": stable_json(taxonomy_snapshot()),
            "frequency_rubric_snapshot_json": stable_json(frequency_rubric_snapshot()),
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            "prompt_template_hash": prompt_template_hash(),
            "response_schema_version": RESPONSE_SCHEMA_VERSION,
            "validator_version": VALIDATOR_VERSION,
            "ai_model": run_options["ai_model"],
            "max_items": run_options["max_items"],
            "max_estimated_cost": run_options["max_estimated_cost"],
            "estimated_input_tokens": estimated_input_tokens,
            "estimated_output_tokens": estimated_output_tokens,
            "estimated_cost": estimated_cost,
            "created_by": run_options["created_by"],
        }
        return {
            "run_data": run_data,
            "item_snapshots": item_snapshots,
            "selected_count": selected_count,
            "estimated_input_tokens": estimated_input_tokens,
            "estimated_output_tokens": estimated_output_tokens,
            "estimated_cost": estimated_cost,
            "selection_filter": run_options["selection_filter"],
        }, None

    def create_run(self, prepared_run):
        run_id = self._vocabulary_maintenance_repository.create_run(
            prepared_run["run_data"],
            prepared_run["item_snapshots"],
        )
        return run_id

    def prepare_domain_model_proposal(
        self,
        name,
        scope,
        ai_model,
        max_items=None,
        max_estimated_cost=None,
        domain=None,
        context=None,
        frequency_band=None,
        created_after=None,
        ids=None,
        source_name=None,
        source_author=None,
        created_by=None,
    ):
        run_options, error = self._clean_run_options(
            name=name,
            scope=scope,
            ai_model=ai_model,
            max_items=max_items,
            max_estimated_cost=max_estimated_cost,
            domain=domain,
            context=context,
            frequency_band=frequency_band,
            created_after=created_after,
            ids=ids,
            source_name=source_name,
            source_author=source_author,
            created_by=created_by,
        )
        if error:
            return None, error

        item_snapshots = self._vocabulary_maintenance_repository.selected_entry_snapshots(
            run_options["filters"],
            run_options["max_items"],
        )
        selected_count = len(item_snapshots)
        estimated_input_tokens = min(
            DOMAIN_MODEL_AGGREGATED_BASE_INPUT_TOKENS
            + selected_count * DOMAIN_MODEL_ESTIMATED_INPUT_TOKENS_PER_ITEM,
            DOMAIN_MODEL_AGGREGATED_MAX_INPUT_TOKENS,
        )
        estimated_output_tokens = DOMAIN_MODEL_ESTIMATED_OUTPUT_TOKENS
        estimated_cost = self._estimate_cost(
            estimated_input_tokens,
            estimated_output_tokens,
        )
        if (
            run_options["max_estimated_cost"] is not None
            and estimated_cost > run_options["max_estimated_cost"]
        ):
            return None, (
                f"Estimated cost {estimated_cost:.2f} exceeds max "
                f"{run_options['max_estimated_cost']:.2f}"
            )

        return {
            "name": run_options["name"],
            "ai_model": run_options["ai_model"],
            "entries": [
                snapshot["source_snapshot"]
                for snapshot in item_snapshots
            ],
            "selection_filter": run_options["selection_filter"],
            "selected_count": selected_count,
            "estimated_input_tokens": estimated_input_tokens,
            "estimated_output_tokens": estimated_output_tokens,
            "estimated_cost": estimated_cost,
            "created_by": run_options["created_by"],
        }, None

    def generate_domain_model_proposal(
        self,
        prepared_proposal,
        api_key,
        timeout_seconds=None,
        max_output_tokens=None,
    ):
        proposal, error = self._vocabulary_ai_service.generate_domain_model(
            prepared_proposal["entries"],
            list(active_vocabulary_domains()),
            list(VOCABULARY_CONTEXTS),
            api_key,
            prepared_proposal["ai_model"],
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
        )
        if error:
            return None, error

        proposal_data = {
            "name": prepared_proposal["name"],
            "selection_filter_json": stable_json(prepared_proposal["selection_filter"]),
            "selected_count": prepared_proposal["selected_count"],
            "ai_model": prepared_proposal["ai_model"],
            "prompt_template_version": DOMAIN_MODEL_PROMPT_TEMPLATE_VERSION,
            "prompt_template_hash": domain_model_prompt_template_hash(),
            "current_domain_snapshot_json": stable_json(list(active_vocabulary_domains())),
            "context_snapshot_json": stable_json(list(VOCABULARY_CONTEXTS)),
            "proposal_json": stable_json(proposal),
            "rationale": proposal["rationale"],
            "created_by": prepared_proposal["created_by"],
        }
        proposal_id = self._vocabulary_maintenance_repository.create_domain_model_proposal(
            proposal_data,
        )
        return {
            "id": proposal_id,
            "proposal": proposal,
        }, None

    def list_domain_model_proposals(self):
        return self._vocabulary_maintenance_repository.list_domain_model_proposals()

    def get_domain_model_proposal(self, proposal_id):
        proposal = self._vocabulary_maintenance_repository.get_domain_model_proposal(
            proposal_id,
        )
        if not proposal:
            return None
        proposal_data = proposal["proposal"]
        proposal["domains"] = proposal_data.get("domains", [])
        proposal["domain_edges"] = proposal_data.get("domain_edges", [])
        proposal["retired_domains"] = proposal_data.get("retired_domains", [])
        proposal["context_boundary_rules"] = proposal_data.get(
            "context_boundary_rules",
            [],
        )
        proposal["review_notes"] = proposal_data.get("review_notes", [])
        return proposal

    def update_domain_model_proposal_status(
        self,
        proposal_id,
        status,
        reviewed_by=None,
        review_note=None,
    ):
        if status not in {"accepted", "rejected"}:
            return None, "Domain model proposal status is invalid"
        proposal = self.get_domain_model_proposal(proposal_id)
        if not proposal:
            return None, "Domain model proposal was not found"
        if proposal["status"] == status:
            return proposal, None
        updated = self._vocabulary_maintenance_repository.update_domain_model_proposal_status(
            proposal_id,
            status,
            reviewed_by,
            review_note,
        )
        if not updated:
            return None, "Domain model proposal was not found"
        return self.get_domain_model_proposal(proposal_id), None

    def _clean_run_options(
        self,
        name,
        scope,
        ai_model,
        max_items,
        max_estimated_cost,
        domain,
        context,
        frequency_band,
        created_after,
        ids,
        source_name,
        source_author,
        created_by,
    ):
        name = str(name or "").strip()
        scope = str(scope or "").strip().lower()
        ai_model = str(ai_model or "").strip()
        if not name:
            return None, "Maintenance run name is required"
        if scope not in MAINTENANCE_SCOPES:
            return None, "Maintenance scope is invalid"
        if not ai_model:
            return None, "Maintenance AI model is required"

        max_items = self._clean_positive_int(max_items)
        if max_items is False:
            return None, "Max items must be a positive integer"
        max_estimated_cost = self._clean_nonnegative_float(max_estimated_cost)
        if max_estimated_cost is False:
            return None, "Max estimated cost must be a non-negative number"

        filters = {}
        selection_filter = {"scope": scope}
        if scope == "missing-domains":
            filters["missing_domains"] = True
        elif scope == "domain":
            domain = str(domain or "").strip().lower()
            if domain not in active_vocabulary_domains():
                return None, "A valid --domain is required for domain scope"
            filters["domain"] = domain
            selection_filter["domain"] = domain
        elif scope == "context":
            context = normalize_context_string(context)
            if not context:
                return None, "A valid --context is required for context scope"
            filters["context"] = context
            selection_filter["context"] = context
        elif scope == "frequency-band":
            frequency_band = str(frequency_band or "").strip().lower().replace("-", "_")
            if frequency_band not in ALLOWED_FREQUENCY_BANDS:
                return None, "A valid --frequency-band is required for frequency-band scope"
            filters["frequency_band"] = frequency_band
            selection_filter["frequency_band"] = frequency_band
        elif scope == "created-after":
            created_after = str(created_after or "").strip()
            if not created_after:
                return None, "--created-after is required for created-after scope"
            filters["created_after"] = created_after
            selection_filter["created_after"] = created_after
        elif scope == "ids":
            vocabulary_ids = self._clean_ids(ids)
            if not vocabulary_ids:
                return None, "--ids is required for ids scope"
            filters["ids"] = vocabulary_ids
            selection_filter["ids"] = vocabulary_ids
        elif scope == "source":
            source_name = str(source_name or "").strip()
            source_author = str(source_author or "").strip()
            if not source_name and not source_author:
                return None, "--source-name or --source-author is required for source scope"
            filters["source_name"] = source_name
            filters["source_author"] = source_author
            selection_filter["source_name"] = source_name
            selection_filter["source_author"] = source_author

        selection_filter["max_items"] = max_items
        return {
            "name": name,
            "scope": scope,
            "ai_model": ai_model,
            "max_items": max_items,
            "max_estimated_cost": max_estimated_cost,
            "filters": filters,
            "selection_filter": selection_filter,
            "created_by": created_by,
        }, None

    def _clean_positive_int(self, value):
        if value in (None, ""):
            return None
        try:
            value = int(value)
        except (TypeError, ValueError):
            return False
        if value <= 0:
            return False
        return value

    def _clean_nonnegative_float(self, value):
        if value in (None, ""):
            return None
        try:
            value = float(value)
        except (TypeError, ValueError):
            return False
        if value < 0:
            return False
        return value

    def _clean_ids(self, value):
        if isinstance(value, (list, tuple)):
            raw_values = value
        else:
            raw_values = str(value or "").replace(";", ",").split(",")
        ids = []
        seen = set()
        for raw_value in raw_values:
            raw_value = str(raw_value).strip()
            if not raw_value.isdigit():
                continue
            vocabulary_id = int(raw_value)
            if vocabulary_id > 0 and vocabulary_id not in seen:
                ids.append(vocabulary_id)
                seen.add(vocabulary_id)
        return ids

    def _estimate_cost(self, input_tokens, output_tokens):
        return ((input_tokens + output_tokens) / 1000) * MAINTENANCE_ESTIMATED_COST_PER_1K_TOKENS


vocabulary_maintenance_service = VocabularyMaintenanceService()
