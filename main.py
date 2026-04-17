from state_machine import StateMachineEngine

def main():
    engine = StateMachineEngine('response.json')

    while not engine.completed:
        question = engine.get_current_question()
        if question is None:
            break

        print(f"Question: {question['question']}")
        if question['type'] == 'single_choice':
            print(f"Options: {question['options']}")
            answer = input("Your choice: ")
        elif question['type'] == 'boolean':
            answer = input("Yes/No: ").lower() in ['yes', 'y', 'true']
        elif question['type'] == 'number':
            answer = float(input("Number: "))
        else:
            answer = input("Answer: ")

        result = engine.answer_question(answer)
        print(result['message'])
        print()

    print("All answers:", engine.get_all_answers())

if __name__ == "__main__":
    main()