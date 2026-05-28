from Repositories.training_repository import training_repository as default_training_repository
from Repositories.vocabulary_repository import (
    vocabulary_repository as default_vocabulary_repository,
)

MAX_TRAINING_VOCABS = 50


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
        if self._has_duplicate_definitions(vocabulary_ids):
            return None, "Training selection contains duplicate definitions"
        vocabs = [
            self._vocabulary_repository.get_entry(vocabulary_id)
            for vocabulary_id in vocabulary_ids
        ]

        training_session_id = self._training_repository.create_training_session(
            user_id,
            vocabs,
        )
        return self.get_training_session(training_session_id, user_id), None

    def get_training_session(self, training_session_id, user_id):
        training_session = self._training_repository.get_training_session(
            training_session_id,
            user_id,
        )
        if not training_session:
            return None

        training_session["vocabs"] = training_session["items"]
        training_session["questions"] = self._build_questions(training_session)
        return training_session

    def get_training_quiz(self, training_session_id, user_id):
        training_session = self.get_training_session(training_session_id, user_id)
        if not training_session:
            return None
        return self._to_quiz_response(training_session)

    def submit_training_session(self, training_session_id, user_id, answers):
        training_session = self.get_training_session(training_session_id, user_id)
        if not training_session:
            return None, "Training session was not found"
        if training_session["submitted_at"] is not None:
            return None, "Training session has already been submitted"
        answers, error = self._clean_answers(answers)
        if error:
            return None, "Invalid answers"
        if not self._answers_match_training(answers, training_session):
            return None, "Invalid answers"

        incorrect_vocabs = []
        correct_count = 0
        total_count = len(training_session["vocabs"])

        for question in training_session["questions"]:
            vocab = question["vocab"]
            selected_option_token = answers.get(question["token"])
            correct_option = self._find_correct_option(question)
            selected_option = self._find_option(question, selected_option_token)
            if selected_option_token == correct_option["token"]:
                correct_count += 1
            else:
                incorrect_vocabs.append(
                    {
                        "id": vocab["id"],
                        "word": vocab["word"],
                        "correct_definition": vocab["definition"],
                        "selected_definition": selected_option["definition"]
                        if selected_option
                        else None,
                    }
                )

        result = {
            "training_session_id": training_session_id,
            "score": correct_count,
            "total": total_count,
            "incorrect_vocabs": incorrect_vocabs,
        }
        saved = self._training_repository.save_training_result(
            training_session_id,
            correct_count,
            total_count,
            incorrect_vocabs,
        )
        if not saved:
            return None, "Training session has already been submitted"
        return result, None

    def get_training_result(self, training_session_id, user_id):
        return self._training_repository.get_training_result(training_session_id, user_id)

    def get_latest_training_vocabulary_ids(self, user_id):
        return self._training_repository.get_latest_training_vocabulary_ids(user_id)

    def _build_questions(self, training_session):
        vocabs_by_id = {
            vocab["vocabulary_id"]: vocab
            for vocab in training_session["vocabs"]
        }
        options_by_question = {}
        for option in training_session["answer_options"]:
            options_by_question.setdefault(option["question_token"], []).append(
                {
                    "token": option["option_token"],
                    "vocabulary_id": option["option_vocabulary_id"],
                    "definition": option["option_definition"],
                }
            )

        questions = []
        for item in training_session["items"]:
            vocab = vocabs_by_id[item["vocabulary_id"]]
            questions.append(
                {
                    "token": item["question_token"],
                    "vocab": {
                        "id": vocab["vocabulary_id"],
                        "word": vocab["word"],
                        "context": vocab["context"],
                        "definition": vocab["definition"],
                    },
                    "options": options_by_question[item["question_token"]],
                }
            )
        return questions

    def _to_quiz_response(self, training_session):
        return {
            "id": training_session["id"],
            "submitted_at": training_session["submitted_at"],
            "questions": [
                {
                    "token": question["token"],
                    "vocab": {
                        "word": question["vocab"]["word"],
                        "context": question["vocab"]["context"],
                    },
                    "options": [
                        {
                            "token": option["token"],
                            "definition": option["definition"],
                        }
                        for option in question["options"]
                    ],
                }
                for question in training_session["questions"]
            ],
        }

    def _clean_vocabulary_ids(self, vocabulary_ids):
        if not vocabulary_ids:
            return None, "Choose at least one vocabulary entry"
        if not isinstance(vocabulary_ids, (list, tuple)):
            return None, "Invalid vocabulary selection"
        if len(vocabulary_ids) > MAX_TRAINING_VOCABS:
            return None, f"Choose at most {MAX_TRAINING_VOCABS} vocabulary entries"

        cleaned_ids = []
        seen_ids = set()
        for vocabulary_id in vocabulary_ids:
            cleaned_id = self._parse_positive_int(vocabulary_id)
            if cleaned_id is None:
                return None, "Invalid vocabulary selection"
            if cleaned_id not in seen_ids:
                cleaned_ids.append(cleaned_id)
                seen_ids.add(cleaned_id)

        return cleaned_ids, None

    def _clean_answers(self, answers):
        if answers is None:
            return {}, None
        if not isinstance(answers, dict):
            return None, "Invalid answers"

        cleaned_answers = {}
        for key, value in answers.items():
            if not isinstance(key, str) or not isinstance(value, str):
                return None, "Invalid answers"
            cleaned_answers[key] = value

        return cleaned_answers, None

    def _parse_positive_int(self, value):
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if value > 0 else None
        if isinstance(value, str) and value.isdigit():
            parsed_value = int(value)
            return parsed_value if parsed_value > 0 else None
        return None

    def _find_correct_option(self, question):
        for option in question["options"]:
            if option["vocabulary_id"] == question["vocab"]["id"]:
                return option
        return None

    def _find_option(self, question, option_token):
        for option in question["options"]:
            if option["token"] == option_token:
                return option
        return None

    def _answers_match_training(self, answers, training_session):
        question_tokens = {question["token"] for question in training_session["questions"]}
        if set(answers.keys()) != question_tokens:
            return False

        questions_by_token = {
            question["token"]: question
            for question in training_session["questions"]
        }
        for question_token, option_token in answers.items():
            if self._find_option(questions_by_token[question_token], option_token) is None:
                return False
        return True

    def _has_duplicate_definitions(self, vocabulary_ids):
        normalized_definitions = []
        for vocabulary_id in vocabulary_ids:
            vocab = self._vocabulary_repository.get_entry(vocabulary_id)
            normalized_definitions.append(self._normalize_definition(vocab["definition"]))
        return len(normalized_definitions) != len(set(normalized_definitions))

    def _normalize_definition(self, definition):
        return " ".join(definition.lower().split())


training_service = TrainingService()
