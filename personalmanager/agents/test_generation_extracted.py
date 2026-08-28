"""
Run: python test_generation_extracted.py path/to/your.pdf [max_questions]

Tests ONLY the generation phase, using pdfplumber-extracted text (fast,
CPU-only, no vision cost) instead of vision-transcribed text. Isolates
how long generation alone takes on this hardware, as a direct comparison
point against the vision-transcribed version.
"""
import os
import sys
import time
from types import SimpleNamespace

import pdfplumber
from openai import OpenAI
from dotenv import load_dotenv

from main import Quiz, QuizEvaluation, EXAMPLE_QUIZ_ITEM

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("API_BASE_URL"))

MAX_RETRIES = 3


def extract_pdf_text(pdf_path):
    full_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            full_text.append(page_text)

            tables = page.extract_tables()
            for i, table in enumerate(tables, start=1):
                full_text.append(f"\n[Table {i} on page {page_num} — extracted with structure preserved:]")
                for row in table:
                    clean_row = [(cell or "").strip().replace("\n", " ") for cell in row]
                    full_text.append(" | ".join(clean_row))

    return "\n".join(full_text)


def create_quiz_text(quiz_details, source_text, feedback=None):
    system_message = """
    You are the most experienced Quiz Master known for creating questions from source material
    for relevant exams. Rely strictly on the source material provided — do not use outside knowledge.
    """
    instructions_text = f"""
        User Requirements:
        Topic: {quiz_details.quiz_topic}
        Exam: {quiz_details.exam_name}
        Difficulty: {quiz_details.difficulty}
        Description: {quiz_details.description}
        Instructions: {quiz_details.tips_for_quiz_creation}
        Number of Questions To Create: {quiz_details.max_questions}

        Create the quiz questionnaire from the source document below.
        Do generate the specified number of questions.
        Do make sure each question has 4 options to choose from.

        Here is an example of a single well-formed quiz item:
        {EXAMPLE_QUIZ_ITEM}

        <source_document>
        {source_text}
        </source_document>
    """
    if feedback:
        instructions_text += f"""

        Your previous attempt had these issues:
        {feedback}

        Output ONLY the corrected quiz as structured JSON — do not restate,
        discuss, or explain the feedback itself in your response.
        """

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


pdf_path = sys.argv[1]
max_questions = int(sys.argv[2]) if len(sys.argv) > 2 else 10

quiz_details = SimpleNamespace(
    quiz_topic="Polity",
    exam_name="UPSC Prelims",
    difficulty="Hard",
    description="Constitutional Foundations notes",
    tips_for_quiz_creation="Create difficult, well-grounded questions",
    max_questions=max_questions,
)

print("Extracting text with pdfplumber (fast, CPU-only, no model calls)...")
t0 = time.time()
source_text = extract_pdf_text(pdf_path)
extract_time = time.time() - t0
print(f"Extraction complete: {extract_time:.1f}s")
print(f"Source text length: {len(source_text)} characters\n")

print("=== Generation (using pdfplumber-extracted text) ===")
t1 = time.time()
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
    print(f"Feedback: {evaluation.feedback}\n")
    if evaluation.status == "Approved":
        break
    feedback = evaluation.feedback

generation_time = time.time() - t1

print(f"\n{'=' * 60}")
print(f"Extraction time:    {extract_time:.1f}s")
print(f"Generation time:    {generation_time:.1f}s ({generation_time / 60:.1f} min)")
print(f"Attempts:           {attempts}")
print(f"Status:             {evaluation.status if evaluation else 'N/A'}")
if questionnaire:
    print(f"Questions generated: {len(questionnaire.quiz_items)}")
print(f"{'=' * 60}")