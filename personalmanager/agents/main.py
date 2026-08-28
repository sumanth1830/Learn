import os
from enum import Enum
from typing import Annotated, List

from dotenv import load_dotenv
from openai import OpenAI
import pdfplumber
from pydantic import BaseModel, Field
from typing_extensions import Literal


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

class ApprovedOrRejected(BaseModel):
    status: Annotated[Literal["Approved", "Rejected"], Field(description="Status of the Evaluation")]


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
    hint: Annotated[str, Field(description="A helpful suggestion or a clue which helps to figure out the answer.")]
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

EXAMPLE_QUIZ_ITEM = """{
  "question": "Regarding the appointment of the Advocate General, what is the qualification required?",
  "options": [
    "Must be qualified to be a judge of the Supreme Court.",
    "Must be qualified to be a judge of a High Court.",
    "Must be an advocate of a High Court for at least 10 years.",
    "Must be a member of the state legislature."
  ],
  "answer": "B",
  "hint": "Look at the 'Law Officers' table.",
  "explanation": "The Advocate General must be qualified to be a judge of a High Court.",
  "question_type": "single choice question"
}"""


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
                
                Here is an example of a single well-formed quiz item, showing
                the exact format and quality expected for every item:
 
                {EXAMPLE_QUIZ_ITEM}
 
                Notice what makes this example good — model every item on
                these same properties:
                - Exactly 4 options, each short (under ~15 words), each a
                  distinct, plausible answer — not restated variations of
                  each other, and not narration about the question itself.
                - "answer" is a single letter (A, B, C, or D) pointing at
                  the correct option — never a description or multiple
                  letters.
                - "hint" points to WHERE in the material to look, without
                  giving away the answer itself.
                - "explanation" is one or two sentences, stating the fact
                  directly from the source — not a restatement of the
                  question, and not speculation beyond what the source says.
 
                If a question doesn't cleanly reduce to 4 short, distinct
                options this way, restructure it — for example, turn a
                multi-condition rule into combination-style options (e.g.
                "Conditions 1 and 2 only", "All three conditions", "Condition
                1 only") rather than merging multiple facts into a single
                option or leaving any option incomplete.
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
            
            Here is an example of a single well-formed quiz item, showing
            the exact format and quality expected for every item:

            {EXAMPLE_QUIZ_ITEM}

            Notice what makes this example good — model every item on
            these same properties:
            - Exactly 4 options, each short (under ~15 words), each a
              distinct, plausible answer — not restated variations of
              each other, and not narration about the question itself.
            - "answer" is a single letter (A, B, C, or D) pointing at
              the correct option — never a description or multiple
              letters.
            - "hint" points to WHERE in the material to look, without
              giving away the answer itself.
            - "explanation" is one or two sentences, stating the fact
              directly from the source — not a restatement of the
              question, and not speculation beyond what the source says.

            If a question doesn't cleanly reduce to 4 short, distinct
            options this way, restructure it — for example, turn a
            multi-condition rule into combination-style options (e.g.
            "Conditions 1 and 2 only", "All three conditions", "Condition
            1 only") rather than merging multiple facts into a single
            option or leaving any option incomplete.
                
            Your previous questionnaire had the following issues:
            {feedback}
            
            Create the revised questionnaire addressing the pointed out issues.
            Be precise and ensure all the requirements are satisfied.
            Do provide a brief explanation (1-3 sentences) for each question,
            grounded strictly in the source material, explaining why the correct answer is correct.
            Also provide hints for each question which helps the students arrive at the answer.

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
            temperature=0.2
        )

        return response.choices[0].message.parsed


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
        
        Please evaluate the Proposed Questionnaire against the specified User
        Requirements and the <source_document>. These are judgment calls that
        require reading comprehension — do not comment on question count or
        option count, those are already verified separately.
 
        Confirm whether each of these is fully satisfied:

        1. Is the difficulty of the questions aligned with the requested
           difficulty level for this exam?
        2. Are the questions contextually valid, logically sound, and
           unambiguous?
        3. Are the questions — and critically, each marked correct answer —
           strictly and accurately derived from the <source_document>? Flag
           anything hallucinated, or any case where the labeled correct
           answer is not actually correct according to the source.
        4. Is each explanation accurate and clearly grounded in the source
           material, not just plausible-sounding?
 
        If ALL constraints are fully satisfied, begin your response with exactly:
        "APPROVED: This questionnaire meets all requirements."
 
        Otherwise, list specifically which requirements are NOT met and provide
        detailed feedback for how to modify the questionnaire to meet those
        requirements.

        """

        # response = client.chat.completions.create(
        #     model=os.getenv("EVAL_MODEL_NAME"),
        #     messages=[
        #         {"role": "system", "content": system_message},
        #         {"role": "user", "content": user_message}
        #     ],
        #     temperature=0.1
        # )
        # return response.choices[0].message.content

        response = client.beta.chat.completions.parse(
            model=os.getenv("EVAL_MODEL_NAME"),
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            response_format=ApprovedOrRejected,
        )

        parsed_output = response.choices[0].message.parsed
        return parsed_output.status


def generate_and_evaluate_quiz(quiz_details, pdf_path):
    """Attempt to create a quiz meeting all constraints using an optimization loop."""
    creator = QuizCreatorAgent()
    evaluator = QuizEvaluatorAgent()

    generated_questionnaire = None
    feedback = None
    attempts = 0
    evaluation = None

    for attempt in range(MAX_RETRIES):
        attempts += 1
        print(f"\n--- Attempt #{attempts} ---")

        generated_questionnaire = creator.create_quiz(quiz_details, pdf_path, feedback)
        evaluation_status = evaluator.evaluate(quiz_details, pdf_path, generated_questionnaire)

        print(f"\n📋 Evaluation Result:")
        print(evaluation)

        # Check for approval prefix
        if evaluation_status.upper() == "APPROVED":
            print("\n✅ All requirements satisfied!")
            break
        else:
            feedback = evaluation
            print("\n⚠️ Requirements not met. Retrying with evaluator feedback...")

    return generated_questionnaire, evaluation, attempts


# if __name__ == "__main__":
#     print("Questionnaire Generator")
#     print("\nCreating optimized questionnaire...")
#
#     quiz_details = {
#         'pdf_path': "../tmp_uploads/7f1fd131-8c44-437d-8deb-41bc361a1814_Polity_01_Constitutional_Foundations.pdf",
#         'topic': 'Polity',
#         'exam_name': 'UPSC Prelims',
#         'difficulty': 'Hard',
#         'max_questions': 20,
#         'description': "Polity Notes for Constitutional_Foundations",
#         'tips_for_quiz_creation': 'Create difficult questions',
#     }
#
#     quiz_result, evaluation, attempts = generate_and_evaluate_quiz(quiz_details)
#
#     print(f"\nAttempts: {attempts}")
#     if "APPROVED" in evaluation.upper():
#         print("✅ All requirements satisfied!")
#     else:
#         print("⚠️ Could not satisfy all requirements after maximum retries.")
#
#     # Iterate and display each question item
#     if quiz_result and hasattr(quiz_result, 'quiz_items'):
#         print(f"\n================ Generated Quiz ({len(quiz_result.quiz_items)} Questions) ================\n")
#
#         for idx, item in enumerate(quiz_result.quiz_items, 1):
#             # FIXED: Read item.question_type (Enum) and item.question (str)
#             print(f"Q{idx}. [{item.question_type.value.upper()}] {item.question}")
#             print("Options:")
#             for opt_idx, option in enumerate(item.answer, 1):
#                 print(f"   {chr(64 + opt_idx)}. {option}")  # Prints A., B., C., D.
#
#             print(f"✓ Correct Answer(s): {', '.join(item.correct_answers)}")
#             print("-" * 60)
#     else:
#         print("\nFailed to generate a valid structured quiz.")
