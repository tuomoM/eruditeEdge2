# Major Change Plan: Versioned Vocabulary Categorization Maintenance

## Goal

Build an admin-only maintenance workflow that can reassess vocabulary categorization in batches without touching production values until review and explicit promotion.

The first target is better domain, context, and frequency classification. The workflow must support stronger AI models than normal vocabulary generation, preserve production safety, and make it possible to compare, accept, reject, promote, and roll back proposed changes.

## Core Principle

Do not overwrite production vocabulary during AI generation.

AI maintenance creates versioned proposals. Production values change only through an explicit promotion step that is validated, conflict-aware, auditable, and reversible.

## Key Problems To Solve

- Current domains and contexts may not categorize vocabulary well enough.
- AI currently overuses broad categories and may mark rare words as common because they are common in model training data.
- Some words need categorization by sense, not just spelling.
- Admin needs a safe way to run stronger, slower, more expensive reassessment jobs in batches.
- Production data must remain stable while experiments are reviewed.

## Revised Architecture

Use versioned maintenance runs rather than a full copied production database as the first implementation.

Each run materializes a set of vocabulary ids and stores proposed values separately from production. A run acts like a candidate classification layer over the current vocabulary.

This gives most of the benefit of a versioned vocabulary database while avoiding the complexity of forking all vocabulary, examples, sources, synonyms, training data, and user ownership.

## Data Model

### `vocabulary_maintenance_runs`

Stores immutable run-level configuration and status.

Suggested fields:

- `id`
- `name`
- `status`
  - `draft`
  - `ready`
  - `running`
  - `completed`
  - `partially_failed`
  - `promoted`
  - `rolled_back`
  - `failed`
- `selection_filter_json`
- `selected_count`
- `taxonomy_snapshot_json`
- `frequency_rubric_snapshot_json`
- `prompt_template_version`
- `prompt_template_hash`
- `response_schema_version`
- `validator_version`
- `ai_model`
- `max_items`
- `max_estimated_cost`
- `estimated_input_tokens`
- `estimated_output_tokens`
- `actual_input_tokens`
- `actual_output_tokens`
- `actual_cost`
- `created_by`
- `created_at`
- `started_at`
- `completed_at`
- `promoted_at`
- `error_summary`

Important: freeze run configuration at creation. Do not allow a run to silently continue under a different taxonomy, prompt, schema, or model.

### `vocabulary_maintenance_items`

Stores one materialized vocabulary entry in a run.

Suggested fields:

- `id`
- `run_id`
- `vocabulary_id`
- `item_status`
  - `pending`
  - `claimed`
  - `generated`
  - `validated`
  - `accepted`
  - `rejected`
  - `stale_conflict`
  - `promoted`
  - `failed`
- `source_snapshot_json`
- `source_snapshot_hash`
- `source_updated_at`
- `proposed_context`
- `proposed_frequency_band`
- `proposed_frequency_note`
- `proposed_domains_json`
  - ordered array matching production domain order
  - first item is primary domain
- `proposed_needs_attention`
- `model_confidence`
- `review_priority`
- `rationale`
- `alternate_domains_json`
- `needs_sense_review`
- `sense_note`
- `raw_response_excerpt`
- `parsed_response_json`
- `validation_errors_json`
- `failure_type`
  - `api_transient`
  - `api_permanent`
  - `invalid_json`
  - `validation_failed`
  - `conflict`
  - `budget_exceeded`
- `attempts`
- `claimed_by`
- `claimed_at`
- `lease_expires_at`
- `generated_at`
- `reviewed_by`
- `reviewed_at`
- `rejection_note`
- `promoted_at`

### `vocabulary_maintenance_promotions`

Stores promotion audit and rollback data.

Suggested fields:

- `id`
- `run_id`
- `item_id`
- `vocabulary_id`
- `before_json`
- `after_json`
- `promoted_by`
- `promoted_at`
- `rolled_back_by`
- `rolled_back_at`

## Taxonomy Snapshot

A maintenance run must store the taxonomy it used, not only a version label.

Snapshot should include:

- allowed domains in order
- max domain count
- domain definitions
- inclusion rules
- exclusion rules
- examples
- counterexamples
- tie-breakers

Primary domain definition:

> The domain in which an educated learner is most likely to need contextual help recognizing this word today.

Secondary domains:

> Meaningful alternate learning contexts, not every possible association.

## Frequency Rubric

The model must not classify frequency by model familiarity or training-data exposure.

Frequency should estimate educated-reader encounter likelihood.

Suggested bands:

- `common`: ordinary adult-reader vocabulary
- `occasional`: known to many educated readers, but not everyday
- `specialized`: common inside a domain, uncommon generally
- `literary`: encountered mainly in literature or serious prose
- `rare`: low encounter likelihood even for educated readers
- `archaic_or_obsolete`: primarily historical, obsolete, or archaic use

The AI must provide a short frequency rationale naming the likely encounter context, such as newspapers, serious nonfiction, classic literature, legal writing, medical writing, theology, or technical manuals.

Examples:

- `awning` should not automatically be `common`; it may be `occasional`.
- `loam` should not automatically be `common`; it may be `specialized` or `literary` depending on intended learner context.

## Semantic Guardrails

Structured JSON validation is necessary but not enough.

Add semantic validators:

- proposed domains must be 1 to max domain count
- domains must be allowed values
- domains must be unique and ordered
- primary domain must be present
- context must not be vague filler
- context length must be bounded
- frequency band must be allowed
- frequency note must be bounded
- rationale is required
- obvious all-default outputs are flagged
- changed primary domain increases review priority
- low confidence increases review priority
- multiple plausible domains increases review priority
- suspected polysemy sets `needs_sense_review`

Store `model_confidence`, but do not trust it as review priority.

Compute separate `review_priority` from risk signals.

## Sense Handling

Categorization belongs to a word sense, not merely a spelling.

The model should be allowed to flag:

- `needs_sense_review`
- `sense_note`
- possible alternate senses

If a vocabulary entry appears to represent multiple learner-relevant senses, the maintenance item should not be auto-promoted.

Examples:

- `hobble` as noun: riding restraint
- `hobble` as verb: impaired movement
- `canon` as church law, accepted literature, music form, or standard

## AI Model Configuration

Add a separate maintenance model setting:

```bash
OPENAI_MAINTENANCE_MODEL=gpt-5.1
```

Fallback may be `OPENAI_MODEL`, but the fallback must be explicit in command output and admin status.

Maintenance commands should print:

- app environment
- database path
- selected item count
- AI model
- prompt version
- estimated cost
- dry-run or production mode

In production, require an explicit confirmation flag for expensive or promotive actions.

## Batch Processing

Commands should be resumable and small.

Suggested commands:

```bash
flask --app app create-vocabulary-maintenance-run \
  --name domain-frequency-v2 \
  --scope all \
  --max-items 500 \
  --max-estimated-cost 10.00 \
  --dry-run
```

```bash
flask --app app process-vocabulary-maintenance-run RUN_ID --limit 25
```

```bash
flask --app app promote-vocabulary-maintenance-run RUN_ID --dry-run
```

```bash
flask --app app rollback-vocabulary-maintenance-run RUN_ID
```

Possible scopes:

- all vocabulary
- missing domains
- selected domain
- selected context
- selected frequency band
- entries created after date
- explicit vocabulary ids
- source name/author

At run creation, materialize the exact vocabulary ids into `vocabulary_maintenance_items`.

## Locking And Idempotency

Prevent concurrent processing of the same run.

Use a DB-backed lease:

- `claimed_by`
- `claimed_at`
- `lease_expires_at`

Processing flow:

1. Claim pending item in a short transaction.
2. Release DB transaction.
3. Call AI.
4. Save raw response excerpt and parsed proposal in a short transaction.
5. Validate proposal.
6. Mark item `validated` or `failed`.

AI calls must not happen inside DB transactions.

Promotion should be per-item transactional.

## Cost Controls

Before creating or processing a run:

- estimate item count
- estimate token usage
- estimate cost
- require `--max-estimated-cost`
- stop when actual or estimated budget is exceeded

Persist actual usage when API returns it.

Failure should be fail-closed.

## Promotion Rules

Promotion must be explicit and conflict-aware.

Before promotion:

- item must be accepted or otherwise eligible
- production snapshot hash must still match
- production `updated_at` must not conflict
- proposed values must still validate against current production rules

If production has changed since snapshot:

- mark item `stale_conflict`
- do not promote
- require manual review

Promotion updates only intended fields:

- ordered domains
- context
- frequency band
- frequency note

It must preserve:

- word
- definition
- examples
- cloze sentences
- sources
- synonyms
- created_by

Promotion must write an audit row with before/after JSON.

## Rollback

Provide rollback by run or item.

Rollback should:

- read `vocabulary_maintenance_promotions`
- restore before snapshot
- only proceed if the target entry still exists
- optionally detect if the entry changed after promotion and mark rollback conflict

## Admin UI

Implement after CLI flow is stable.

Pages:

- run list
- run detail summary
- item review list
- item diff page
- promotion preview

Run detail should show:

- status counts
- selected item count
- processed count
- failed count
- conflict count
- estimated and actual cost
- model and prompt version
- taxonomy version/snapshot label

Item review should show:

- current vs proposed domains
- current vs proposed context
- current vs proposed frequency
- rationale collapsed by default
- alternate plausible domains
- review priority
- validation errors
- accept/reject controls

Promotion preview should show aggregate deltas:

- domain distribution before/after
- primary domain changes
- frequency distribution before/after
- top changed domains
- low-confidence count
- `needs_attention` count
- conflict count

Bulk promotion should exclude:

- conflicts
- failed validation
- rejected items
- low-confidence or high-review-priority items
- items with `needs_attention`

Large bulk promotions should require typed confirmation.

## Evaluation Set

Before trusting a new taxonomy/prompt/model, create a locked challenge set.

Include:

- polysemous words
- archaic words
- technical words
- religious vocabulary
- philosophical vocabulary
- legal vocabulary
- literary vocabulary
- false friends
- etymologically misleading words
- words whose modern use differs from historical origin

Use this set to compare prompt/model versions before broad runs.

## Railway Operations

Expected production flow:

1. Deploy code.
2. Run migrations.
3. Confirm database path/volume.
4. Create maintenance run with dry-run first.
5. Create real run with budget and scope.
6. Process in small batches:

```bash
flask --app app process-vocabulary-maintenance-run RUN_ID --limit 25
```

7. Review admin dashboard.
8. Promote eligible items with dry-run first.
9. Promote real run/items with production confirmation.
10. Monitor conflicts and failures.

Never require one giant long-running command.

## Suggested Implementation Phases

### Phase 1: Foundations

- Add migration for maintenance run/item/promotion tables.
- Add config for `OPENAI_MAINTENANCE_MODEL`.
- Add taxonomy snapshot and frequency rubric constants.
- Add repository/service for run creation.
- Add CLI dry-run creation command.

### Phase 2: Batch AI Processing

- Add AI reassessment method with strict schema.
- Add item claiming and leasing.
- Add process-batch command.
- Add validation and failure classification.
- Add token/cost tracking where available.

### Phase 3: Review

- Add admin run list and run detail.
- Add item diff/review UI.
- Add accept/reject item actions.
- Add aggregate distribution comparison.

### Phase 4: Promotion

- Add promotion service.
- Add optimistic concurrency checks.
- Add promotion audit rows.
- Add dry-run promotion command.
- Add real promotion command with confirmation.

### Phase 5: Rollback And Refinement

- Add rollback command.
- Add rollback UI if needed.
- Build evaluation set.
- Iterate taxonomy and frequency rubric.

## Non-Goals For First Version

- Do not fork the entire production vocabulary database.
- Do not update production during AI generation.
- Do not run large maintenance jobs from web request handlers.
- Do not allow automatic promotion without admin review.
- Do not treat AI confidence as correctness.

## Open Questions

- Should context become a controlled vocabulary, or remain free text?
- Should frequency bands replace current values or extend them?
- Should `specialized` and `literary` be separate from frequency, or part of frequency?
- Should maintenance support comparing two AI models on the same run?
- How large should the locked evaluation set be before first real promotion?
- How much raw AI response should be retained for audit without storing too much user-provided text?

## Success Criteria

- Admin can create a maintenance run without changing production.
- Run materializes exact selected vocabulary ids.
- Batch processing can be stopped and resumed.
- Proposals are validated against taxonomy and frequency rubrics.
- Admin can compare current vs proposed values.
- Promotion is conflict-aware and auditable.
- Rollback is possible for promoted items.
- Stronger maintenance model can be configured independently from normal AI generation.
- Aggregate statistics show whether the new categorization improves domain and frequency distribution.
