import json


class StateMachineEngine:

    def __init__(self, json_file):

        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.questions = data["questions"]

        self.question_map = {
            q["ref"]: q for q in self.questions
        }

        self.question_order = [
            q["ref"] for q in self.questions
        ]

    def _normalize_answer_key(self, answer):
        """Normalize answer keys to handle whitespace differences."""
        if answer is None:
            return ""
        
        if isinstance(answer, bool):
            return "Yes" if answer else "No"
        
        # Convert to string and normalize whitespace
        normalized = str(answer).strip()
        # Collapse multiple whitespace characters to single space
        return " ".join(normalized.split())

    def get_question(self, ref):

        return self.question_map.get(str(ref).strip())

    # ---------------------------------------------------
    # FIRST QUESTION
    # ---------------------------------------------------

    def get_first_question(self):

        return self.questions[0]

    # ---------------------------------------------------
    # NEXT QUESTION
    # ---------------------------------------------------

    def get_next_question_ref(self, current_ref, answer):

        question = self.get_question(current_ref)

        if not question:
            return {"status": "error", "message": "Question not found"}

        q_type = question.get("type")

        # -----------------------------------------------
        # CLEAN NUMERIC INPUT
        # -----------------------------------------------

        if q_type in ["numeric", "number", "price", "counter"]:

            if isinstance(answer, str):

                answer = (
                    answer
                    .replace(",", "")
                    .replace("£", "")
                    .strip()
                )

            try:
                answer = float(answer)

            except:
                return {
                    "status": "error",
                    "message": "Please enter a valid number."
                }

        # -----------------------------------------------
        # REQUIRED VALIDATION
        # -----------------------------------------------

        if question.get("required"):

            if answer is None or answer == "":
                return {
                    "status": "error",
                    "message": "This question is required."
                }

        # -----------------------------------------------
        # HANDLER NEXT
        # -----------------------------------------------

        handler_next = question.get("handlerNext")

        if handler_next and isinstance(handler_next, dict):

            normalized_key = self._normalize_answer_key(answer)

            # Create normalized version of handler_next keys
            normalized_handler_next = {
                self._normalize_answer_key(k): v
                for k, v in handler_next.items()
            }

            next_config = normalized_handler_next.get(normalized_key)

            # Boolean compatibility
            if next_config is None:
                if answer is True:
                    next_config = normalized_handler_next.get("Yes")
                elif answer is False:
                    next_config = normalized_handler_next.get("No")

            if next_config:

                action = next_config.get("action")

                # OPEN QUESTION
                if action == "open_question":

                    next_ref = next_config.get("ref")
                    if next_ref:
                        return {
                            "status": "success",
                            "next_ref": str(next_ref).strip()
                        }

                # END FLOW
                if action in [
                    "navigate_to_screen",
                    "to_save_and_finish_with_error"
                ]:

                    return {
                        "status": "completed"
                    }

        # -----------------------------------------------
        # DEFAULT NEXT QUESTION
        # -----------------------------------------------

        try:

            current_ref_str = str(current_ref).strip()
            
            if current_ref_str not in self.question_order:
                return {"status": "completed"}
            
            idx = self.question_order.index(current_ref_str)

            next_idx = idx + 1

            if next_idx >= len(self.question_order):

                return {
                    "status": "completed"
                }

            return {
                "status": "success",
                "next_ref": self.question_order[next_idx]
            }

        except Exception as e:
            print(f"DEBUG: Error in default navigation: {e}")
            return {
                "status": "completed"
            }
