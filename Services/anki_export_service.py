import html
import os
import tempfile
import zipfile


ANKI_DECK_ID = 2059400110
ANKI_MODEL_ID = 2059400111


class AnkiExportService:
    def export_vocabulary_entries(self, entries, deck_name="Erudite Edge Vocabulary"):
        package_path = self.export_vocabulary_entries_to_file(entries, deck_name)
        try:
            with open(package_path, "rb") as package_file:
                return package_file.read()
        finally:
            os.unlink(package_path)

    def export_vocabulary_entries_to_file(self, entries, deck_name="Erudite Edge Vocabulary"):
        try:
            import genanki
        except ImportError as error:
            raise RuntimeError("Anki export dependency is not installed") from error

        deck = genanki.Deck(ANKI_DECK_ID, deck_name)
        model = genanki.Model(
            ANKI_MODEL_ID,
            "Erudite Edge Vocabulary",
            fields=[
                {"name": "Word"},
                {"name": "Context"},
                {"name": "Definition"},
                {"name": "PartOfSpeech"},
                {"name": "Domains"},
                {"name": "Synonyms"},
                {"name": "Examples"},
                {"name": "ClozeSentences"},
            ],
            templates=[
                {
                    "name": "Vocabulary",
                    "qfmt": (
                        "<h1>{{Word}}</h1>"
                        "{{#Context}}<p><em>{{Context}}</em></p>{{/Context}}"
                    ),
                    "afmt": (
                        "{{FrontSide}}"
                        "<hr id=\"answer\">"
                        "<p>{{Definition}}</p>"
                        "{{#PartOfSpeech}}<p><strong>Part of speech:</strong> {{PartOfSpeech}}</p>{{/PartOfSpeech}}"
                        "{{#Domains}}<p><strong>Domains:</strong> {{Domains}}</p>{{/Domains}}"
                        "{{#Synonyms}}<p><strong>Synonyms:</strong> {{Synonyms}}</p>{{/Synonyms}}"
                        "{{#Examples}}<p><strong>Examples:</strong><br>{{Examples}}</p>{{/Examples}}"
                        "{{#ClozeSentences}}<p><strong>Cloze:</strong><br>{{ClozeSentences}}</p>{{/ClozeSentences}}"
                    ),
                }
            ],
        )

        for entry in entries:
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
                    self._list_field(entry.get("cloze_sentences", [])),
                ],
                guid=genanki.guid_for("erudite-edge-vocabulary", entry["id"]),
            )
            deck.add_note(note)

        package_path = self._write_package(genanki.Package(deck))
        self._validate_package_file(package_path)
        return package_path

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
