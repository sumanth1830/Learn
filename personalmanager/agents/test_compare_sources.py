"""
Run: python test_compare_sources.py [max_questions]

Runs the identical generation pipeline against BOTH source texts —
PaddleOCR output vs Gemma4-vision-transcribed output — for a direct,
apples-to-apples comparison. Same quiz_details, same prompt, same
retry logic, only the source text differs between the two runs.
"""
import os
import sys
import time
from types import SimpleNamespace

from openai import OpenAI
from dotenv import load_dotenv

from main import Quiz, QuizEvaluation, EXAMPLE_QUIZ_ITEM

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("API_BASE_URL"))

MAX_RETRIES = 3


def create_quiz_text(quiz_details, source_text, feedback=None):
    system_message = """
    You are the most experienced Quiz Master known for creating questions from source material
    for relevant exams. Rely strictly on the source material provided — do not use outside knowledge.
    """
    instructions_text = f"""
Before writing your final answer, briefly consider which fact in the source
material is specific and non-obvious enough to make a genuinely challenging
question — in one or two sentences only, not more.

Then generate exactly {quiz_details.max_questions} multiple choice question{'s' if quiz_details.max_questions != 1 else ''}, each with
4 options, one correct answer letter, a hint, and an explanation, based
strictly on the following source document.

<source_document>
{source_text}
</source_document>
"""
    if feedback:
        instructions_text += f"\n\nYour previous attempt had these issues:\n{feedback}\nOutput ONLY the corrected quiz as structured JSON — do not restate or discuss the feedback."

    response = client.beta.chat.completions.parse(
        model=os.getenv("MODEL_NAME"),
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": instructions_text},
        ],
        response_format=Quiz,
        temperature=0.2,
    )
    return response.choices[0].message.parsed


def evaluate_text(quiz_details, source_text, questionnaire):
    system_message = "You are a meticulous professor whose job is to find any and all violations of requirements."
    questionnaire_str = questionnaire.model_dump_json(indent=2)
    instructions_text = f"""
Proposed Questionnaire:
{questionnaire_str}

<source_document>
{source_text}
</source_document>

Set status to "Approved" only if fully satisfied, else "Rejected" with specific feedback.
"""
    response = client.beta.chat.completions.parse(
        model=os.getenv("EVAL_MODEL_NAME"),
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": instructions_text},
        ],
        temperature=0.1,
        response_format=QuizEvaluation,
    )
    return response.choices[0].message.parsed


def run_pipeline(label, source_text, quiz_details):
    print(f"\n{'#' * 60}")
    print(f"# {label}")
    print(f"{'#' * 60}")
    print(f"Source text length: {len(source_text)} characters")

    t0 = time.time()
    feedback = None
    questionnaire = None
    evaluation = None
    attempts = 0

    for attempt in range(MAX_RETRIES):
        attempts += 1
        print(f"--- Attempt #{attempts} ---")
        try:
            questionnaire = create_quiz_text(quiz_details, source_text, feedback)
        except Exception as e:
            print(f"Creator failed: {e}")
            feedback = f"Previous attempt failed: {e}"
            continue

        evaluation = evaluate_text(quiz_details, source_text, questionnaire)
        print(f"Evaluation: {evaluation.status}")
        if evaluation.status != "Approved":
            print(f"Feedback: {evaluation.feedback}")
        if evaluation.status == "Approved":
            break
        feedback = evaluation.feedback

    elapsed = time.time() - t0

    print(f"\nTime: {elapsed:.1f}s | Attempts: {attempts} | Status: {evaluation.status if evaluation else 'N/A'}")
    if questionnaire:
        for i, item in enumerate(questionnaire.quiz_items, 1):
            print(f"\nQ{i}: {item.question}")
            print(f"   Options: {item.options}")
            print(f"   Answer: {item.answer}")
            print(f"   Explanation: {item.explanation}")

    return {
        "label": label, "time": elapsed, "attempts": attempts,
        "status": evaluation.status if evaluation else "N/A",
    }


max_questions = int(sys.argv[1]) if len(sys.argv) > 1 else 10

quiz_details = SimpleNamespace(
    quiz_topic="Polity",
    exam_name="UPSC Prelims",
    difficulty="Hard",
    description="Constitutional Foundations notes",
    tips_for_quiz_creation="Create difficult, well-grounded questions",
    max_questions=max_questions,
)

with open("paddleocr_output.txt") as f:
    paddleocr_text = f.read()

with open("transcribed_text_nothink.txt") as f:
    gemma_text = f.read()

results = [
    run_pipeline("PaddleOCR source", paddleocr_text, quiz_details),
    run_pipeline("Gemma4-vision source", gemma_text, quiz_details),
]

print(f"\n\n{'=' * 60}")
print("SUMMARY")
print(f"{'=' * 60}")
for r in results:
    print(f"{r['label']:25s} | {r['time']:6.1f}s | {r['attempts']} attempt(s) | {r['status']}")