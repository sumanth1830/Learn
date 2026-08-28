import os
from enum import Enum
from typing import Annotated, List

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from typing_extensions import Literal

from pdf_to_images import pdf_to_base64_images

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("API_BASE_URL"))

MAX_RETRIES = 3


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

    # Re-add your options field_validator here (content-quality checks —
    # leaked reasoning, embedded newlines, duplicates). Unchanged from before.


class Quiz(BaseModel):
    quiz_items: Annotated[List[QuizItem], Field(description="List of quiz items")]


class QuizEvaluation(BaseModel):
    status: Annotated[Literal["Approved", "Rejected"], Field(description="Status of the Evaluation")]
    feedback: Annotated[
        str,
        Field(description=(
            "If Rejected, specific, actionable feedback on exactly which "
            "requirements are not met and how to fix them. If Approved, "
            "a brief confirmation sentence is fine."
        ))
    ]


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


def _build_image_content(images):
    """Shared helper — both agents build the same image-block list from an
    already-rendered images array, rather than each re-rendering the PDF."""
    return [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
        for img_b64 in images
    ]


class QuizCreatorAgent:
    def create_quiz(self, quiz_details, images, feedback=None):
        print("Generating Questionnaire....")

        system_message = """
        You are the most experienced Quiz Master known for creating questions from source material
        for relevant exams. You have astounding subject knowledge and years of experience creating
        questionnaires. Rely strictly on the source material provided as images — do not use outside
        knowledge, and do not merge content from different tables or columns together.
        """

        instructions_text = f"""
            User Requirements:
            Topic: {quiz_details.quiz_topic}
            Exam: {quiz_details.exam_name}
            Difficulty: {quiz_details.difficulty}
            Description: {quiz_details.description}
            Instructions: {quiz_details.tips_for_quiz_creation}
            Number of Questions To Create: {quiz_details.max_questions}

            Create the quiz questionnaire from the attached page images, as per the user
            requirements and the difficulty level of the exam.
            Do strictly follow the user requirements and instructions.
            Do generate the specified number of questions.
            Do make sure each question has 4 options to choose from.
            Please generate a quiz based strictly on the content shown in the attached
            images — read tables carefully, and don't merge content from different
            tables or columns together.

            Here is an example of a single well-formed quiz item, showing the exact
            format and quality expected for every item:

            {EXAMPLE_QUIZ_ITEM}

            Notice what makes this example good — model every item on these same
            properties:
            - Exactly 4 options, each short (under ~15 words), each a distinct,
              plausible answer — not restated variations of each other, and not
              narration about the question itself.
            - "answer" is a single letter (A, B, C, or D) pointing at the correct
              option — never a description or multiple letters.
            - "hint" points to WHERE in the material to look, without giving away
              the answer itself.
            - "explanation" is one or two sentences, stating the fact directly from
              the source — not a restatement of the question, and not speculation
              beyond what the source says.

            If a question doesn't cleanly reduce to 4 short, distinct options this
            way, restructure it — for example, turn a multi-condition rule into
            combination-style options (e.g. "Conditions 1 and 2 only", "All three
            conditions", "Condition 1 only") rather than merging multiple facts
            into a single option or leaving any option incomplete.
        """

        if feedback:
            instructions_text += f"""

            Your previous attempt had the following issues:
            {feedback}

            Create a revised questionnaire that specifically addresses these issues.
            """

        content = [{"type": "text", "text": instructions_text}] + _build_image_content(images)

        response = client.beta.chat.completions.parse(
            model=os.getenv("MODEL_NAME"),
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": content},
            ],
            response_format=Quiz,
            temperature=0.2,
        )
        return response.choices[0].message.parsed


class QuizEvaluatorAgent:
    def evaluate(self, quiz_details, images, generated_questionnaire):
        print("Evaluating generated questionnaire....")

        if isinstance(generated_questionnaire, BaseModel):
            questionnaire_str = generated_questionnaire.model_dump_json(indent=2)
        else:
            questionnaire_str = str(generated_questionnaire)

        system_message = """
        You are a meticulous professor whose job is to find any and all violations of requirements.
        You are highly skilled at identifying incorrect questions that do not adhere to exam standards
        or are hallucinated outside the source content. Do not accept approximations. Be accurate,
        strict, and provide corrective feedback.
        """

        instructions_text = f"""
        User Requirements:
        Topic: {quiz_details.quiz_topic}
        Exam: {quiz_details.exam_name}
        Difficulty: {quiz_details.difficulty}
        Description: {quiz_details.description}
        Instructions: {quiz_details.tips_for_quiz_creation}

        Proposed Questionnaire:
        {questionnaire_str}

        The attached images are the actual source material this questionnaire should
        be grounded in. Please evaluate the Proposed Questionnaire against the
        specified User Requirements and the attached images. These are judgment
        calls that require reading comprehension — do not comment on question
        count or option count, those are already verified separately.

        Confirm whether each of these is fully satisfied:
        1. Is the difficulty of the questions aligned with the requested difficulty
           level for this exam?
        2. Are the questions contextually valid, logically sound, and unambiguous?
        3. Are the questions — and critically, each marked correct answer —
           strictly and accurately derived from the attached images? Flag anything
           hallucinated, or any case where the labeled correct answer is not
           actually correct according to the source.
        4. Is each explanation accurate and clearly grounded in the source
           material, not just plausible-sounding?

        Set status to "Approved" only if ALL four are fully satisfied. Otherwise
        set status to "Rejected" and put specific, actionable feedback in the
        feedback field — exactly which requirements are not met and how to fix
        them.
        """

        content = [{"type": "text", "text": instructions_text}] + _build_image_content(images)

        response = client.beta.chat.completions.parse(
            model=os.getenv("EVAL_MODEL_NAME"),
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": content},
            ],
            temperature=0.1,
            response_format=QuizEvaluation,
        )
        return response.choices[0].message.parsed


def generate_and_evaluate_quiz(quiz_details, pdf_path):
    """Attempt to create a quiz meeting all constraints using an optimization loop."""
    creator = QuizCreatorAgent()
    evaluator = QuizEvaluatorAgent()

    # Rendered once here, passed to both agents every attempt — previously
    # each agent re-rendered the same PDF independently, twice per attempt.
    images = pdf_to_base64_images(pdf_path)

    generated_questionnaire = None
    feedback = None
    attempts = 0
    evaluation = None
    last_creator_error = None

    for attempt in range(MAX_RETRIES):
        attempts += 1
        print(f"\n--- Attempt #{attempts} ---")

        # Previously, any exception here (a validation failure, a length-
        # limit error) propagated straight out of this whole function,
        # skipping the retry loop entirely — meaning MAX_RETRIES only ever
        # protected against evaluator rejection, never a creator-side
        # failure. Both real failures seen in testing were exactly this
        # kind — this is the fix.
        try:
            generated_questionnaire = creator.create_quiz(quiz_details, images, feedback)
        except Exception as e:
            print(f"\n⚠️ Creator attempt failed: {e}")
            last_creator_error = str(e)
            feedback = (
                f"Your previous attempt failed with an error: {e}. Make sure "
                f"every question has exactly 4 short, distinct options, and "
                f"keep explanations concise so the full response fits within "
                f"the available length."
            )
            continue

        evaluation = evaluator.evaluate(quiz_details, images, generated_questionnaire)

        print(f"\n📋 Evaluation Result: {evaluation.status}")
        print(evaluation.feedback)

        if evaluation.status == "Approved":
            print("\n✅ All requirements satisfied!")
            break
        else:
            feedback = evaluation.feedback
            print("\n⚠️ Requirements not met. Retrying with evaluator feedback...")

    if generated_questionnaire is None:
        # Every attempt failed at the creator stage itself — raise clearly
        # rather than returning None for tasks.py to crash on obscurely.
        raise RuntimeError(
            f"Failed to generate a valid questionnaire after {attempts} "
            f"attempt(s). Last error: {last_creator_error}"
        )

    evaluation_status = evaluation.status if evaluation else "Rejected"
    return generated_questionnaire, evaluation_status, attempts