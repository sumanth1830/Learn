"""
Run: python test_minimal.py path/to/your.pdf

Strips the prompt down to the absolute bare minimum — no few-shot
example, no "notice what makes this good" explanation, nothing beyond
the schema itself (already enforced structurally via response_format)
and the source text. Tests whether our elaborate instructions are
somehow causing the bloated-response problem, rather than preventing it.
"""
import os
import sys
import time

from openai import OpenAI
from dotenv import load_dotenv

from main import Quiz
from test_generation_extracted import extract_pdf_text

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("API_BASE_URL"))

pdf_path = sys.argv[1]
max_questions = int(sys.argv[2]) if len(sys.argv) > 2 else 1

print("Extracting text...")
source_text = extract_pdf_text(pdf_path)
print(f"Source text length: {len(source_text)} characters\n")

instructions_text = f"""
Generate exactly {max_questions} multiple choice question{'s' if max_questions != 1 else ''}, each with
4 options, one correct answer letter, a hint, and an explanation, based
strictly on the following source document.

<source_document>
{source_text}
</source_document>
"""

print(f"Sending minimal request for {max_questions} question(s)...")
t0 = time.time()

response = client.beta.chat.completions.parse(
    model=os.getenv("MODEL_NAME"),
    messages=[{"role": "user", "content": instructions_text}],
    response_format=Quiz,
    temperature=0.2,
)

elapsed = time.time() - t0
usage = response.usage

print(f"\n{'=' * 60}")
print(f"Time: {elapsed:.1f}s")
print(f"Prompt tokens: {usage.prompt_tokens}")
print(f"Completion tokens: {usage.completion_tokens}")
print(f"Total tokens: {usage.total_tokens}")
print(f"{'=' * 60}")

quiz = response.choices[0].message.parsed
if quiz:
    for item in quiz.quiz_items:
        print(f"\nQ: {item.question}")
        print(f"Options: {item.options}")
        print(f"Answer: {item.answer}")