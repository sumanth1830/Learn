"""
Run: python test_timing.py path/to/your.pdf [max_questions]

Tests generate_and_evaluate_quiz() directly, no Django/Celery involved —
fast local iteration for measuring real generation time and confirming
the retry-catching fix actually works.
"""
import sys
import time
from types import SimpleNamespace

from main import generate_and_evaluate_quiz

pdf_path = sys.argv[1]
max_questions = int(sys.argv[2]) if len(sys.argv) > 2 else 10

# SimpleNamespace gives us an object with .attribute access (matching what
# the real Django Quiz model instance provides) without needing Django
# running at all for this test.
quiz_details = SimpleNamespace(
    quiz_topic="Polity",
    exam_name="UPSC Prelims",
    difficulty="Hard",
    description="Constitutional Foundations notes",
    tips_for_quiz_creation="Create difficult, well-grounded questions",
    max_questions=max_questions,
)

print(f"PDF: {pdf_path}")
print(f"Requesting {max_questions} question(s)...\n")

start = time.time()

try:
    quiz, status, attempts = generate_and_evaluate_quiz(quiz_details, pdf_path)
    elapsed = time.time() - start

    print(f"\n{'=' * 60}")
    print(f"Status:              {status}")
    print(f"Attempts:            {attempts}")
    print(f"Total time:          {elapsed:.1f}s ({elapsed / 60:.1f} min)")
    print(f"Questions generated: {len(quiz.quiz_items)}")
    print(f"{'=' * 60}")

except Exception as e:
    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"FAILED after {elapsed:.1f}s ({elapsed / 60:.1f} min)")
    print(f"Error: {e}")
    print(f"{'=' * 60}")