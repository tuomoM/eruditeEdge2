import json

import db


class VocabularyMaintenanceRepository:
    def create_run(self, run_data, item_snapshots):
        connection = db.get_connection()
        try:
            cursor = connection.execute(
                """
                INSERT INTO vocabulary_maintenance_runs
                    (
                        name,
                        status,
                        selection_filter_json,
                        selected_count,
                        taxonomy_snapshot_json,
                        frequency_rubric_snapshot_json,
                        prompt_template_version,
                        prompt_template_hash,
                        response_schema_version,
                        validator_version,
                        ai_model,
                        max_items,
                        max_estimated_cost,
                        estimated_input_tokens,
                        estimated_output_tokens,
                        created_by
                    )
                VALUES (?, 'ready', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    run_data["name"],
                    run_data["selection_filter_json"],
                    run_data["selected_count"],
                    run_data["taxonomy_snapshot_json"],
                    run_data["frequency_rubric_snapshot_json"],
                    run_data["prompt_template_version"],
                    run_data["prompt_template_hash"],
                    run_data["response_schema_version"],
                    run_data["validator_version"],
                    run_data["ai_model"],
                    run_data["max_items"],
                    run_data["max_estimated_cost"],
                    run_data["estimated_input_tokens"],
                    run_data["estimated_output_tokens"],
                    run_data.get("created_by"),
                ],
            )
            run_id = cursor.lastrowid
            for snapshot in item_snapshots:
                connection.execute(
                    """
                    INSERT INTO vocabulary_maintenance_items
                        (
                            run_id,
                            vocabulary_id,
                            item_status,
                            source_snapshot_json,
                            source_snapshot_hash,
                            source_updated_at
                        )
                    VALUES (?, ?, 'pending', ?, ?, ?)
                    """,
                    [
                        run_id,
                        snapshot["vocabulary_id"],
                        snapshot["source_snapshot_json"],
                        snapshot["source_snapshot_hash"],
                        snapshot["source_updated_at"],
                    ],
                )
            connection.commit()
            return run_id
        except Exception:
            connection.rollback()
            raise

    def selected_entry_snapshots(self, filters, max_items=None):
        where = []
        params = []
        joins = []

        if filters.get("ids"):
            placeholders = ", ".join("?" for _ in filters["ids"])
            where.append(f"vocabulary_entries.id IN ({placeholders})")
            params.extend(filters["ids"])
        if filters.get("missing_domains"):
            where.append(
                """
                NOT EXISTS (
                    SELECT 1
                    FROM vocabulary_domains
                    WHERE vocabulary_domains.vocabulary_id = vocabulary_entries.id
                )
                """
            )
        if filters.get("domain"):
            where.append(
                """
                EXISTS (
                    SELECT 1
                    FROM vocabulary_domains
                    WHERE vocabulary_domains.vocabulary_id = vocabulary_entries.id
                        AND vocabulary_domains.domain = ?
                )
                """
            )
            params.append(filters["domain"])
        if filters.get("context"):
            where.append(
                """
                (
                    ';' || lower(
                        replace(
                            replace(
                                replace(
                                    replace(vocabulary_entries.context, '/', ';'),
                                    ',',
                                    ';'
                                ),
                                '; ',
                                ';'
                            ),
                            ' ;',
                            ';'
                        )
                    ) || ';'
                ) LIKE ?
                """
            )
            params.append(f"%;{filters['context'].lower()};%")
        if filters.get("frequency_band"):
            where.append("vocabulary_entries.frequency_band = ?")
            params.append(filters["frequency_band"])
        if filters.get("created_after"):
            where.append("vocabulary_entries.created_at >= ?")
            params.append(filters["created_after"])
        if filters.get("source_name") or filters.get("source_author"):
            joins.extend(
                [
                    """
                    JOIN vocabulary_entry_sources
                        ON vocabulary_entry_sources.vocabulary_id = vocabulary_entries.id
                    """,
                    """
                    JOIN vocabulary_sources
                        ON vocabulary_sources.id = vocabulary_entry_sources.source_id
                    """,
                ]
            )
            if filters.get("source_name"):
                where.append("vocabulary_sources.name LIKE ? COLLATE NOCASE")
                params.append(f"%{filters['source_name']}%")
            if filters.get("source_author"):
                where.append("vocabulary_sources.author LIKE ? COLLATE NOCASE")
                params.append(f"%{filters['source_author']}%")

        where_sql = "WHERE " + " AND ".join(where) if where else ""
        limit_sql = "LIMIT ?" if max_items else ""
        if max_items:
            params.append(max_items)

        rows = db.query(
            f"""
            SELECT DISTINCT
                vocabulary_entries.id,
                vocabulary_entries.word,
                vocabulary_entries.definition,
                vocabulary_entries.context,
                vocabulary_entries.part_of_speech,
                vocabulary_entries.frequency_band,
                vocabulary_entries.frequency_note,
                vocabulary_entries.needs_attention,
                vocabulary_entries.confidence_score,
                vocabulary_entries.updated_at
            FROM vocabulary_entries
            {' '.join(joins)}
            {where_sql}
            ORDER BY vocabulary_entries.id
            {limit_sql}
            """,
            params,
        )
        return [
            self._snapshot_from_row(dict(row))
            for row in rows
        ]

    def create_domain_model_proposal(self, proposal_data):
        cursor = db.execute(
            """
            INSERT INTO vocabulary_domain_model_proposals
                (
                    name,
                    selection_filter_json,
                    selected_count,
                    ai_model,
                    prompt_template_version,
                    prompt_template_hash,
                    current_domain_snapshot_json,
                    context_snapshot_json,
                    proposal_json,
                    rationale,
                    created_by
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                proposal_data["name"],
                proposal_data["selection_filter_json"],
                proposal_data["selected_count"],
                proposal_data["ai_model"],
                proposal_data["prompt_template_version"],
                proposal_data["prompt_template_hash"],
                proposal_data["current_domain_snapshot_json"],
                proposal_data["context_snapshot_json"],
                proposal_data["proposal_json"],
                proposal_data["rationale"],
                proposal_data.get("created_by"),
            ],
        )
        return cursor.lastrowid

    def list_domain_model_proposals(self):
        rows = db.query(
            """
            SELECT
                id,
                name,
                status,
                selected_count,
                ai_model,
                created_at,
                reviewed_at
            FROM vocabulary_domain_model_proposals
            ORDER BY created_at DESC, id DESC
            """
        )
        return [dict(row) for row in rows]

    def get_domain_model_proposal(self, proposal_id):
        rows = db.query(
            """
            SELECT *
            FROM vocabulary_domain_model_proposals
            WHERE id = ?
            """,
            [proposal_id],
        )
        if not rows:
            return None
        proposal = dict(rows[0])
        for key in (
            "selection_filter_json",
            "current_domain_snapshot_json",
            "context_snapshot_json",
            "proposal_json",
        ):
            proposal[key.replace("_json", "")] = json.loads(proposal[key])
        return proposal

    def _snapshot_from_row(self, entry):
        vocabulary_id = entry["id"]
        snapshot = {
            "id": vocabulary_id,
            "word": entry["word"],
            "definition": entry["definition"],
            "context": entry["context"],
            "part_of_speech": entry["part_of_speech"],
            "frequency_band": entry["frequency_band"],
            "frequency_note": entry["frequency_note"],
            "needs_attention": entry["needs_attention"],
            "confidence_score": entry["confidence_score"],
            "domains": self._entry_domains(vocabulary_id),
            "examples": self._entry_examples(vocabulary_id),
            "sources": self._entry_sources(vocabulary_id),
            "updated_at": entry["updated_at"],
        }
        snapshot_json = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        return {
            "vocabulary_id": vocabulary_id,
            "source_snapshot": snapshot,
            "source_snapshot_json": snapshot_json,
            "source_updated_at": entry["updated_at"],
        }

    def _entry_domains(self, vocabulary_id):
        rows = db.query(
            """
            SELECT domain
            FROM vocabulary_domains
            WHERE vocabulary_id = ?
            ORDER BY domain_order
            """,
            [vocabulary_id],
        )
        return [row["domain"] for row in rows]

    def _entry_examples(self, vocabulary_id):
        rows = db.query(
            """
            SELECT example_sentence
            FROM vocabulary_examples
            WHERE vocabulary_id = ?
            ORDER BY example_order
            """,
            [vocabulary_id],
        )
        return [row["example_sentence"] for row in rows]

    def _entry_sources(self, vocabulary_id):
        rows = db.query(
            """
            SELECT
                vocabulary_sources.name,
                vocabulary_sources.author,
                vocabulary_sources.source_type,
                vocabulary_entry_sources.note
            FROM vocabulary_entry_sources
            JOIN vocabulary_sources
                ON vocabulary_sources.id = vocabulary_entry_sources.source_id
            WHERE vocabulary_entry_sources.vocabulary_id = ?
            ORDER BY vocabulary_entry_sources.source_order
            """,
            [vocabulary_id],
        )
        return [dict(row) for row in rows]


vocabulary_maintenance_repository = VocabularyMaintenanceRepository()
