import json
import unittest

from Services.vocabulary_ai_service import VocabularyAiService


class FakeResponses:
    def __init__(self, output_text):
        self.output_text = output_text
        self.last_request = None

    def create(self, **kwargs):
        self.last_request = kwargs
        return self


class FakeClient:
    def __init__(self, output_text):
        self.responses = FakeResponses(output_text)


class VocabularyAiServiceTestCase(unittest.TestCase):
    def valid_output(self):
        return json.dumps(
            {
                "word": "operation",
                "definition": "A planned activity or procedure.",
                "context": "Scientific/Medical",
                "part_of_speech": "noun",
                "domains": ["communication", "body"],
                "synonyms": ["procedure", "process"],
                "examples": [
                    "The operation required careful preparation.",
                    "The rescue operation continued through the night.",
                ],
                "cloze_sentences": [
                    "The ____ required careful preparation.",
                    "The rescue ____ continued through the night.",
                ],
            }
        )

    def test_generate_entry_uses_only_the_word_in_the_prompt(self):
        client = FakeClient(self.valid_output())
        service = VocabularyAiService(client=client)

        entry, error = service.generate_entry("operation", "test-key", "test-model")

        self.assertIsNone(error)
        self.assertEqual(entry["word"], "operation")
        self.assertEqual(client.responses.last_request["input"], "Word: operation")
        self.assertEqual(client.responses.last_request["model"], "test-model")
        self.assertIn(
            "context field must describe the usage setting",
            client.responses.last_request["instructions"],
        )
        self.assertIn(
            "Keep context separate from domains",
            client.responses.last_request["instructions"],
        )
        context_schema = (
            client.responses.last_request["text"]["format"]["schema"]["properties"]["context"]
        )
        self.assertIn("not an example sentence", context_schema["description"])
        self.assertIn("separate from semantic domains", context_schema["description"])
        self.assertIn("Provide 2-4 example sentences", client.responses.last_request["instructions"])
        examples_schema = (
            client.responses.last_request["text"]["format"]["schema"]["properties"]["examples"]
        )
        self.assertEqual(examples_schema["minItems"], 2)
        domains_schema = (
            client.responses.last_request["text"]["format"]["schema"]["properties"]["domains"]
        )
        self.assertEqual(domains_schema["minItems"], 1)
        self.assertEqual(domains_schema["maxItems"], 4)
        self.assertIn("emotion", domains_schema["items"]["enum"])
        self.assertIn("body", domains_schema["items"]["enum"])
        self.assertIn("quality", domains_schema["items"]["enum"])
        self.assertIn("reasoning", domains_schema["items"]["enum"])
        self.assertIn("truth", domains_schema["items"]["enum"])
        self.assertIn("independent of usage settings", domains_schema["description"])
        self.assertEqual(entry["domains"], ["communication", "body"])

    def test_generate_entry_normalizes_sentence_like_context_to_general(self):
        output = json.dumps(
            {
                "word": "stultify",
                "definition": "To make ineffective.",
                "context": "The excessive regulations served to stultify innovation.",
                "part_of_speech": "verb",
                "domains": ["change", "power"],
                "synonyms": ["hinder"],
                "examples": [
                    "The rigid process stultified the team.",
                    "Outdated rules can stultify creative work.",
                ],
                "cloze_sentences": [
                    "The rigid process could ____ the team.",
                    "Outdated rules can ____ creative work.",
                ],
            }
        )
        service = VocabularyAiService(client=FakeClient(output))

        entry, error = service.generate_entry("stultify", "test-key", "test-model")

        self.assertIsNone(error)
        self.assertEqual(entry["context"], "General")

    def test_generate_entry_accepts_slash_separated_context_categories(self):
        output = json.dumps(
            {
                "word": "stultify",
                "definition": "To make ineffective.",
                "context": "Business / Formal",
                "part_of_speech": "verb",
                "domains": ["power", "change"],
                "synonyms": ["hinder"],
                "examples": [
                    "The rigid process stultified the team.",
                    "Excessive approvals can stultify a promising project.",
                ],
                "cloze_sentences": [
                    "The rigid process could ____ the team.",
                    "Excessive approvals can ____ a promising project.",
                ],
            }
        )
        service = VocabularyAiService(client=FakeClient(output))

        entry, error = service.generate_entry("stultify", "test-key", "test-model")

        self.assertIsNone(error)
        self.assertEqual(entry["context"], "Business/Formal")

    def test_generate_entry_preserves_multi_word_context_category(self):
        output = json.dumps(
            {
                "word": "stultify",
                "definition": "To make ineffective.",
                "context": "Business English",
                "part_of_speech": "verb",
                "domains": ["power", "change"],
                "synonyms": ["hinder"],
                "examples": [
                    "The rigid process stultified the team.",
                    "Poor incentives may stultify workplace initiative.",
                ],
                "cloze_sentences": [
                    "The rigid process could ____ the team.",
                    "Poor incentives may ____ workplace initiative.",
                ],
            }
        )
        service = VocabularyAiService(client=FakeClient(output))

        entry, error = service.generate_entry("stultify", "test-key", "test-model")

        self.assertIsNone(error)
        self.assertEqual(entry["context"], "Business English")

    def test_generate_entry_replaces_unsupported_two_word_context_with_general(self):
        output = json.dumps(
            {
                "word": "stultify",
                "definition": "To make ineffective.",
                "context": "The regulations",
                "part_of_speech": "verb",
                "domains": ["power", "change"],
                "synonyms": ["hinder"],
                "examples": [
                    "The rigid process stultified the team.",
                    "The policy threatened to stultify debate.",
                ],
                "cloze_sentences": [
                    "The rigid process could ____ the team.",
                    "The policy threatened to ____ debate.",
                ],
            }
        )
        service = VocabularyAiService(client=FakeClient(output))

        entry, error = service.generate_entry("stultify", "test-key", "test-model")

        self.assertIsNone(error)
        self.assertEqual(entry["context"], "General")

    def test_generate_entry_rejects_ai_output_with_fewer_than_two_examples(self):
        output = json.dumps(
            {
                "word": "stultify",
                "definition": "To make ineffective.",
                "context": "Formal",
                "part_of_speech": "verb",
                "domains": ["power", "change"],
                "synonyms": ["hinder"],
                "examples": ["The rigid process stultified the team."],
                "cloze_sentences": [
                    "The rigid process could ____ the team.",
                    "The policy threatened to ____ debate.",
                ],
            }
        )
        service = VocabularyAiService(client=FakeClient(output))

        entry, error = service.generate_entry("stultify", "test-key", "test-model")

        self.assertIsNone(entry)
        self.assertEqual(error, "OpenAI returned invalid vocabulary data")

    def test_generate_entry_rejects_output_without_domains(self):
        output = json.dumps(
            {
                "word": "stultify",
                "definition": "To make ineffective.",
                "context": "Formal",
                "part_of_speech": "verb",
                "domains": [],
                "synonyms": ["hinder"],
                "examples": [
                    "The rigid process stultified the team.",
                    "The policy threatened to stultify debate.",
                ],
                "cloze_sentences": [
                    "The rigid process could ____ the team.",
                    "The policy threatened to ____ debate.",
                ],
            }
        )
        service = VocabularyAiService(client=FakeClient(output))

        entry, error = service.generate_entry("stultify", "test-key", "test-model")

        self.assertIsNone(entry)
        self.assertEqual(error, "OpenAI returned invalid vocabulary data")

    def test_generate_entry_rejects_sql_injection(self):
        service = VocabularyAiService(client=FakeClient(self.valid_output()))

        entry, error = service.generate_entry(
            "operation'; DROP TABLE users; --",
            "test-key",
            "test-model",
        )

        self.assertIsNone(entry)
        self.assertEqual(error, "Please provide one word only")

    def test_generate_entry_accepts_sql_keyword_as_word(self):
        service = VocabularyAiService(client=FakeClient(self.valid_output()))

        entry, error = service.generate_entry("DROP", "test-key", "test-model")

        self.assertIsNone(error)
        self.assertEqual(entry["word"], "DROP")

    def test_generate_entry_rejects_html_tags(self):
        service = VocabularyAiService(client=FakeClient(self.valid_output()))

        entry, error = service.generate_entry("<b>operation</b>", "test-key", "test-model")

        self.assertIsNone(entry)
        self.assertEqual(error, "Please provide one word only")

    def test_generate_entry_requires_api_key(self):
        service = VocabularyAiService(client=FakeClient(self.valid_output()))

        entry, error = service.generate_entry("operation", "", "test-model")

        self.assertIsNone(entry)
        self.assertEqual(error, "OpenAI API key is missing")

    def test_generate_cloze_data_includes_semantic_domains(self):
        output = json.dumps(
            {
                "part_of_speech": "noun",
                "domains": ["emotion", "cognition"],
                "cloze_sentences": [
                    "She felt deep ____ after the mistake.",
                    "To his ____, the plan failed immediately.",
                ],
            }
        )
        client = FakeClient(output)
        service = VocabularyAiService(client=client)

        result, error = service.generate_cloze_data(
            {
                "word": "chagrin",
                "definition": "Distress caused by humiliation or failure.",
                "context": "Formal",
                "examples": ["She felt chagrin after the mistake."],
            },
            "test-key",
            "test-model",
        )

        self.assertIsNone(error)
        self.assertEqual(result["domains"], ["emotion", "cognition"])
        schema = client.responses.last_request["text"]["format"]["schema"]
        self.assertIn("domains", schema["required"])
        self.assertEqual(schema["properties"]["domains"]["maxItems"], 4)
        self.assertIn(
            "separate from usage context",
            client.responses.last_request["instructions"],
        )

    def test_validate_usage_accepts_correct_sentence(self):
        output = json.dumps({"result": "correct", "hint": ""})
        client = FakeClient(output)
        service = VocabularyAiService(client=client)

        result, error = service.validate_usage(
            {
                "word": "chagrin",
                "definition": "Disappointment or anger.",
                "context": "Formal",
                "examples": ["She felt chagrin after the mistake."],
            },
            "To my chagrin, I forgot the appointment.",
            "test-key",
            "test-model",
        )

        self.assertIsNone(error)
        self.assertEqual(result, {"result": "correct", "hint": ""})
        self.assertIn("Ignore minor grammar", client.responses.last_request["instructions"])
        self.assertIn("Target word: chagrin", client.responses.last_request["input"])
        self.assertEqual(
            client.responses.last_request["text"]["format"]["schema"]["properties"]["result"]["enum"],
            ["correct", "incorrect"],
        )

    def test_validate_usage_returns_incorrect_with_hint(self):
        output = json.dumps(
            {
                "result": "incorrect",
                "hint": "Use chagrin to describe disappointment or embarrassment.",
            }
        )
        service = VocabularyAiService(client=FakeClient(output))

        result, error = service.validate_usage(
            {
                "word": "chagrin",
                "definition": "Disappointment or anger.",
                "context": "Formal",
                "examples": [],
            },
            "The chagrin was very blue.",
            "test-key",
            "test-model",
        )

        self.assertIsNone(error)
        self.assertEqual(result["result"], "incorrect")
        self.assertEqual(
            result["hint"],
            "Use chagrin to describe disappointment or embarrassment.",
        )

    def test_validate_usage_rejects_empty_sentence(self):
        service = VocabularyAiService(client=FakeClient("{}"))

        result, error = service.validate_usage(
            {"word": "chagrin", "definition": "Disappointment.", "examples": []},
            "",
            "test-key",
            "test-model",
        )

        self.assertIsNone(result)
        self.assertEqual(error, "Sentence is required")

    def test_validate_usage_requires_api_key(self):
        service = VocabularyAiService(client=FakeClient("{}"))

        result, error = service.validate_usage(
            {"word": "chagrin", "definition": "Disappointment.", "examples": []},
            "To my chagrin, I was late.",
            "",
            "test-model",
        )

        self.assertIsNone(result)
        self.assertEqual(error, "OpenAI API key is missing")


if __name__ == "__main__":
    unittest.main()
