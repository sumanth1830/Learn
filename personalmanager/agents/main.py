import os
from enum import Enum
from typing import Annotated, List

from dotenv import load_dotenv
from openai import OpenAI
import pdfplumber
from pydantic import BaseModel, Field
from typing_extensions import Literal
import json

# Loading environment variables
load_dotenv()

print("API_BASE_URL =", os.getenv("API_BASE_URL"))
print("OPENAI_API_KEY =", os.getenv("OPENAI_API_KEY"))

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("API_BASE_URL"))

def extract_pdf_text(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())


class QuestionTypeEnums(str, Enum):
    SQ = "single choice question"
    MCQ = "multiple choice question"


class QuizItem(BaseModel):
    question: Annotated[str, Field(description="Question text")]
    options: Annotated[
        List[str],
        Field(description="Exactly 4 answer option strings.", min_length=4, max_length=4),
    ]
    answer: Annotated[
        Literal["A", "B", "C", "D"],
        Field(description="The letter corresponding to the correct option in `options` (A=1st, B=2nd, C=3rd, D=4th).")
    ]
    explanation: Annotated[
        str,
        Field(description=(
            "1-3 sentences explaining why the correct answer is correct, "
            "citing the reasoning or facts from the source document. Must "
            "be grounded strictly in the provided source material — do not "
            "explain using outside knowledge."
        ))
    ]
    question_type: Annotated[
        Literal[QuestionTypeEnums.SQ],
        Field(description="Type of question: single choice")
    ]


class Quiz(BaseModel):
    quiz_items: Annotated[List[QuizItem], Field(description="List of quiz items")]

MAX_RETRIES = 3


class QuizCreatorAgent:
    def create_quiz(self, quiz_details, pdf_path, feedback=None):
        pdf_text = extract_pdf_text(pdf_path)
        print("Generating Questionnaire....")
        system_message = """
        You are most experienced Quiz Master known for creating questions from the material for the relevant exams.
        You have astounding subject knowledge and years of experience creating questionnaires.
        When provided with the relevant details of the quiz, exam type, topic and difficulty level, you can
        read through the provided material and generate a questionnaire as per the given requirements.
        Rely strictly on the source provided in the user prompt.
        """
        #                 Topic: {quiz_details['topic']}
        #                 Exam: {quiz_details['exam_name']}
        #                 Difficulty: {quiz_details['difficulty']}
        #                 Description: {quiz_details['description']}
        #                 Instructions: {quiz_details['tips_for_quiz_creation']}
        #                 Number of Questions To Create: {quiz_details['max_questions']}

        if feedback is None:
            user_message = f"""
                User Requirements:
                Topic: {quiz_details.quiz_topic}
                Exam: {quiz_details.exam_name}
                Difficulty: {quiz_details.difficulty}
                Description: {quiz_details.description}
                Instructions: {quiz_details.tips_for_quiz_creation}
                Number of Questions To Create: {quiz_details.max_questions}
                
                Create the quiz questionnaire from the file provided as per the user requirements and adhering to the difficulty level of the exam mentioned.
                Do strictly follow the user requirements and instructions.
                Do generate the specified number of questions.
                Do make sure each question has 4 options to choose from.
                Please generate a quiz based strictly on the content inside the <source_document> tags.

                <source_document>
                {pdf_text}
                </source_document>
            """

        else:
            system_message = f"""
            You are expert professor in preparing questions for the exams and also well adept in analyzing if the
            questions prepared for the exam match the criteria of the exam or not, and prepare the questions as per the criteria.
            Use the file provided as the material to prepare the questionnaire.
            """

            user_message = f"""
            
            User Requirements:
            Topic: {quiz_details.quiz_topic}
            Exam: {quiz_details.exam_name}
            Difficulty: {quiz_details.difficulty}
            Description: {quiz_details.description}
            Instructions: {quiz_details.tips_for_quiz_creation}
            Number of Questions To Create: {quiz_details.max_questions}
                
            Your previous questionnaire had the following issues:
            {feedback}
            
            Create the revised questionnaire addressing the pointed out issues.
            Be precise and ensure all the requirements are satisfied.
            Do provide a brief explanation (1-3 sentences) for each question,
            grounded strictly in the source material, explaining why the correct answer is correct.

            Please generate a quiz based strictly on the content inside the <source_document> tags.

            <source_document>
            {pdf_text}
            </source_document>
            """

        # response = client.chat.completions.create(
        #     model=os.getenv("MODEL_NAME"),
        #     messages=[
        #         {"role": "system", "content": system_message},
        #         {"role": "user", "content": user_message},
        #     ],
        #     temperature=1  # Higher for more creativity
        # )
        # return response.choices[0].message.content
        response = client.beta.chat.completions.parse(
            model=os.getenv("MODEL_NAME"),
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            response_format=Quiz,  # the new letter-based Quiz/QuizItem from above
            temperature=0.4
        )

        return response.choices[0].message.parsed

        # response = client.chat.completions.create(
        #     model=os.getenv("MODEL_NAME"),
        #     messages=[
        #         {"role": "system", "content": system_message},
        #         {"role": "user", "content": user_message},
        #     ],
        #     response_format={"type": "json_object"},  # ask for JSON, no schema enforcement
        #     temperature=0.4,
        # )
        #
        # raw_content = response.choices[0].message.content
        # print("=" * 60)
        # print("RAW MODEL OUTPUT:")
        # print(raw_content)
        # print("=" * 60)
        #
        # # Now try to see if it's even valid JSON at all
        # try:
        #     parsed_json = json.loads(raw_content)
        #     print(f"Valid JSON. Top-level keys: {list(parsed_json.keys())}")
        #     if "quiz_items" in parsed_json and parsed_json["quiz_items"]:
        #         first_item = parsed_json["quiz_items"][0]
        #         print(f"First item keys: {list(first_item.keys())}")
        #         print(f"First item 'answer' field: {first_item.get('answer')!r}")
        #
        #     return parsed_json
        # except json.JSONDecodeError as e:
        #     print(f"NOT valid JSON: {e}")


class QuizEvaluatorAgent:
    def evaluate(self, quiz_details, pdf_path, generated_questionnaire):
        pdf_text = extract_pdf_text(pdf_path)
        print("Evaluating generated questionnaire....")

        # Handle both raw Pydantic models and strings safely
        if isinstance(generated_questionnaire, BaseModel):
            questionnaire_str = generated_questionnaire.model_dump_json(indent=2)
        else:
            questionnaire_str = str(generated_questionnaire)

        system_message = """
        You are a meticulous professor whose job is to find any and all violations of requirements.
        You are highly skilled at identifying incorrect questions that do not adhere to exam standards or are hallucinated outside the source content.
        Do not accept approximations. Be accurate, strict, and provide corrective feedback.
        """

        user_message = f"""
        User Requirements:
        Topic: {quiz_details.quiz_topic}
        Exam: {quiz_details.exam_name}
        Difficulty: {quiz_details.difficulty}
        Description: {quiz_details.description}
        Instructions: {quiz_details.tips_for_quiz_creation}
        Number of Questions To Create: {quiz_details.max_questions}

        Proposed Questionnaire:
        {questionnaire_str}

        <source_document>
        {pdf_text}
        </source_document>

        Please evaluate the Proposed Questionnaire against all specified User Requirements and the <source_document>.
        Confirm whether each of these constraints is fully satisfied:
        1. Is the difficulty of the questions aligned with the requested difficulty level for this exam?
        2. Is the total number of questions equal to the Number of Questions limit specified?
        3. Are the questions contextually valid and logically sound?
        4. Are the questions strictly derived from the provided <source_document>?
        5. Does each question has 4 options?
        6. Does each question have a clear, source-grounded explanation for
           why its the correct answer?

        If ALL constraints are fully satisfied, begin your response with exactly:
        "APPROVED: This questionnaire meets all requirements."

        Otherwise, list specifically which requirements are NOT met and provide detailed feedback for how to modify 
        the questionnaire to meet those requirements.
        """

        response = client.chat.completions.create(
            model=os.getenv("EVAL_MODEL_NAME"),
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1
        )
        return response.choices[0].message.content


def generate_and_evaluate_quiz(quiz_details, pdf_path):
    """Attempt to create a quiz meeting all constraints using an optimization loop."""
    creator = QuizCreatorAgent()
    evaluator = QuizEvaluatorAgent()

    generated_questionnaire = None
    feedback = None
    attempts = 0

    for attempt in range(MAX_RETRIES):
        attempts += 1
        print(f"\n--- Attempt #{attempts} ---")

        generated_questionnaire = creator.create_quiz(quiz_details, pdf_path, feedback)
        evaluation = evaluator.evaluate(quiz_details, pdf_path, generated_questionnaire)

        print(f"\n📋 Evaluation Result:")
        print(evaluation)

        # Check for approval prefix
        if evaluation.strip().upper().startswith("APPROVED"):
            print("\n✅ All requirements satisfied!")
            break
        else:
            feedback = evaluation
            print("\n⚠️ Requirements not met. Retrying with evaluator feedback...")

    return generated_questionnaire, evaluation, attempts


if __name__ == "__main__":
    print("Questionnaire Generator")
    print("\nCreating optimized questionnaire...")

    quiz_details = {
        'pdf_path': "../tmp_uploads/7f1fd131-8c44-437d-8deb-41bc361a1814_Polity_01_Constitutional_Foundations.pdf",
        'topic': 'Polity',
        'exam_name': 'UPSC Prelims',
        'difficulty': 'Hard',
        'max_questions': 20,
        'description': "Polity Notes for Constitutional_Foundations",
        'tips_for_quiz_creation': 'Create difficult questions',
    }

    quiz_result, evaluation, attempts = generate_and_evaluate_quiz(quiz_details)

    print(f"\nAttempts: {attempts}")
    if "APPROVED" in evaluation.upper():
        print("✅ All requirements satisfied!")
    else:
        print("⚠️ Could not satisfy all requirements after maximum retries.")

    # Iterate and display each question item
    if quiz_result and hasattr(quiz_result, 'quiz_items'):
        print(f"\n================ Generated Quiz ({len(quiz_result.quiz_items)} Questions) ================\n")

        for idx, item in enumerate(quiz_result.quiz_items, 1):
            # FIXED: Read item.question_type (Enum) and item.question (str)
            print(f"Q{idx}. [{item.question_type.value.upper()}] {item.question}")
            print("Options:")
            for opt_idx, option in enumerate(item.answer, 1):
                print(f"   {chr(64 + opt_idx)}. {option}")  # Prints A., B., C., D.

            print(f"✓ Correct Answer(s): {', '.join(item.correct_answers)}")
            print("-" * 60)
    else:
        print("\nFailed to generate a valid structured quiz.")
