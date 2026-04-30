import json

class StateMachineEngine:
    def __init__(self, json_path):
        with open(json_path, 'r') as f:
            self.questions = json.load(f)
        self.question_order = list(self.questions.keys())
        self.current_index = 0
        self.answers = {}
        self.completed = False

    def get_current_question(self):
        if self.current_index >= len(self.question_order):
            self.completed = True
            return None
        key = self.question_order[self.current_index]
        return {**self.questions[key], 'key': key}

    def answer_question(self, answer):
        if self.completed:
            return {"status": "completed", "message": "Questionnaire completed."}

        key = self.question_order[self.current_index]
        question = self.questions[key]

        # Validate answer
        validation_result = self.validate_answer(answer, question)
        if not validation_result['valid']:
            return {"status": "error", "message": validation_result['message']}

        # Store answer
        self.answers[key] = answer

        # Move to next
        self.current_index += 1

        # Skip questions based on conditions
        while self.current_index < len(self.question_order):
            next_key = self.question_order[self.current_index]
            next_q = self.questions[next_key]
            if 'condition' in next_q and not self.evaluate_condition(next_q['condition']):
                self.current_index += 1
            else:
                break

        return {"status": "success", "message": "Answer recorded."}

    def validate_answer(self, answer, question):
        qtype = question['type']
        if qtype == 'single_choice':
            if answer not in question.get('options', []):
                return {"valid": False, "message": question['validation']['error_message']}
        elif qtype == 'boolean':
            if not isinstance(answer, bool):
                return {"valid": False, "message": question['validation']['error_message']}
        elif qtype == 'number':
            # Accept any numeric value
            try:
                num_answer = float(answer) if isinstance(answer, str) else answer
                if 'min_value' in question['validation']:
                    if num_answer < question['validation']['min_value']:
                        return {"valid": False, "message": question['validation']['error_message']}
            except (ValueError, TypeError):
                return {"valid": False, "message": "Please enter a valid number."}
        return {"valid": True}

    def evaluate_condition(self, condition):
        # Replace variables with their values
        for var, value in self.answers.items():
            if isinstance(value, str):
                condition = condition.replace(var, repr(value))
            elif isinstance(value, bool):
                condition = condition.replace(var, str(value))
            else:
                condition = condition.replace(var, str(value))
        # Replace || with or
        condition = condition.replace('||', 'or')
        # Replace && with and if needed, but not in this json
        try:
            return eval(condition)
        except:
            return False

    def get_all_answers(self):
        return self.answers

    def reset(self):
        self.current_index = 0
        self.answers = {}
        self.completed = False