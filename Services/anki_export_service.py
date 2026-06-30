import html
import os
import tempfile
import zipfile


ANKI_DECK_ID = 2059400110
ANKI_DESCRIPTION_MODEL_ID = 2059400111
ANKI_CLOZE_MODEL_ID = 2059400112
ANKI_CARD_TYPE_DESCRIPTION = "description"
ANKI_CARD_TYPE_CLOZE = "cloze"
ANKI_CARD_TYPES = {ANKI_CARD_TYPE_DESCRIPTION, ANKI_CARD_TYPE_CLOZE}


class AnkiExportService:
    def export_vocabulary_entries(
        self,
        entries,
        card_type=ANKI_CARD_TYPE_DESCRIPTION,
        deck_name="Erudite Edge Vocabulary",
    ):
        package_path = self.export_vocabulary_entries_to_file(entries, card_type, deck_name)
        try:
            with open(package_path, "rb") as package_file:
                return package_file.read()
        finally:
            os.unlink(package_path)

    def export_vocabulary_entries_to_file(
        self,
        entries,
        card_type=ANKI_CARD_TYPE_DESCRIPTION,
        deck_name="Erudite Edge Vocabulary",
    ):
        try:
            import genanki
        except ImportError as error:
            raise RuntimeError("Anki export dependency is not installed") from error
        if card_type not in ANKI_CARD_TYPES:
            raise RuntimeError("Anki card type is invalid")

        deck = genanki.Deck(ANKI_DECK_ID, deck_name)
        model = (
            self._cloze_model(genanki)
            if card_type == ANKI_CARD_TYPE_CLOZE
            else self._description_model(genanki)
        )

        for entry in entries:
            if card_type == ANKI_CARD_TYPE_CLOZE:
                self._add_cloze_notes(genanki, deck, model, entry)
            else:
                self._add_description_note(genanki, deck, model, entry)

        if card_type == ANKI_CARD_TYPE_CLOZE and not deck.notes:
            raise RuntimeError("Selected vocabulary has no cloze sentences")

        package_path = self._write_package(genanki.Package(deck))
        self._validate_package_file(package_path)
        return package_path

    def _description_model(self, genanki):
        return genanki.Model(
            ANKI_DESCRIPTION_MODEL_ID,
            "Erudite Edge Description",
            fields=[
                {"name": "Word"},
                {"name": "Context"},
                {"name": "Definition"},
                {"name": "PartOfSpeech"},
                {"name": "Domains"},
                {"name": "Synonyms"},
                {"name": "Examples"},
            ],
            templates=[
                {
                    "name": "Description",
                    "qfmt": (
                        "<h1>{{Word}}</h1>"
                        "{{#Context}}<p><em>{{Context}}</em></p>{{/Context}}"
                    ),
                    "afmt": (
                        "{{FrontSide}}"
                        "<hr id=\"answer\">"
                        "<p>{{Definition}}</p>"
                        "{{#Examples}}<p><strong>Examples:</strong><br>{{Examples}}</p>{{/Examples}}"
                        "{{#PartOfSpeech}}<p><strong>Part of speech:</strong> {{PartOfSpeech}}</p>{{/PartOfSpeech}}"
                        "{{#Domains}}<p><strong>Domains:</strong> {{Domains}}</p>{{/Domains}}"
                        "{{#Synonyms}}<p><strong>Synonyms:</strong> {{Synonyms}}</p>{{/Synonyms}}"
                    ),
                }
            ],
        )

    def _cloze_model(self, genanki):
        return genanki.Model(
            ANKI_CLOZE_MODEL_ID,
            "Erudite Edge Cloze",
            fields=[
                {"name": "ClozeSentence"},
                {"name": "Word"},
                {"name": "Context"},
                {"name": "Definition"},
                {"name": "Examples"},
            ],
            templates=[
                {
                    "name": "Cloze",
                    "qfmt": "<p>{{ClozeSentence}}</p>",
                    "afmt": (
                        "{{FrontSide}}"
                        "<hr id=\"answer\">"
                        "<h1>{{Word}}</h1>"
                        "{{#Context}}<p><em>{{Context}}</em></p>{{/Context}}"
                        "<p>{{Definition}}</p>"
                        "{{#Examples}}<p><strong>Examples:</strong><br>{{Examples}}</p>{{/Examples}}"
                    ),
                }
            ],
        )

    def _add_description_note(self, genanki, deck, model, entry):
        note = genanki.Note(
            model=model,
            fields=[
                self._field(entry["word"]),
                self._field(entry.get("context")),
                self._field(entry["definition"]),
                self._field(entry.get("part_of_speech")),
                self._field(", ".join(entry.get("domains", []))),
                self._field(", ".join(entry.get("synonyms", []))),
                self._list_field(entry.get("examples", [])),
            ],
            guid=genanki.guid_for("erudite-edge-description", entry["id"]),
        )
        deck.add_note(note)

    def _add_cloze_notes(self, genanki, deck, model, entry):
        for index, cloze_sentence in enumerate(entry.get("cloze_sentences", []), start=1):
            note = genanki.Note(
                model=model,
                fields=[
                    self._field(cloze_sentence),
                    self._field(entry["word"]),
                    self._field(entry.get("context")),
                    self._field(entry["definition"]),
                    self._list_field(entry.get("examples", [])),
                ],
                guid=genanki.guid_for("erudite-edge-cloze", entry["id"], index),
            )
            deck.add_note(note)

    def _write_package(self, package):
        descriptor, package_path = tempfile.mkstemp(suffix=".apkg")
        os.close(descriptor)
        package.write_to_file(package_path)
        return package_path

    def _validate_package_file(self, package_path):
        try:
            with zipfile.ZipFile(package_path) as archive:
                bad_file = archive.testzip()
        except zipfile.BadZipFile as error:
            raise RuntimeError("Generated Anki package is not a valid zip archive") from error
        if bad_file:
            raise RuntimeError(f"Generated Anki package contains a corrupt file: {bad_file}")

    def _field(self, value):
        if value is None:
            return ""
        return html.escape(str(value), quote=False)

    def _list_field(self, values):
        return "<br>".join(self._field(value) for value in values)


anki_export_service = AnkiExportService()
