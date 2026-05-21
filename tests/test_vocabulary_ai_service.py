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
                "synonyms": ["procedure", "process"],
                "examples": ["The operation required careful preparation."],
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

    def test_generate_entry_rejects_sql_injection(self):
        service = VocabularyAiService(client=FakeClient(self.valid_output()))

        entry, error = service.generate_entry(
            "operation'; DROP TABLE users; --",
            "test-key",
            "test-model",
        )

        self.assertIsNone(entry)
        self.assertEqual(error, "Please provide one word only")

    def test_generate_entry_rejects_sql_keyword(self):
        service = VocabularyAiService(client=FakeClient(self.valid_output()))

        entry, error = service.generate_entry("DROP", "test-key", "test-model")

        self.assertIsNone(entry)
        self.assertEqual(error, "Please provide one word only")

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


if __name__ == "__main__":
    unittest.main()
