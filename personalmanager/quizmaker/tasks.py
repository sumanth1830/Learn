import os
from celery import shared_task
from .models import Question, Answer, Quiz
from agents.main import generate_and_evaluate_quiz
from celery.exceptions import SoftTimeLimitExceeded

def _normalize(s):
    return s.strip().lower()


@shared_task
def generate_quiz_task(quiz_id, pdf_path):
    print("Generating Quiz....")
    try:
        quiz = Quiz.objects.get(pk=quiz_id)
    except Quiz.DoesNotExist:
        return

    quiz.status = "PROCESSING"
    quiz.save(update_fields=["status"])

    try:
        generated_quiz, _, _ = generate_and_evaluate_quiz(quiz, pdf_path)

        print(f"[quiz {quiz.pk}] requested max_questions={quiz.max_questions}, "
              f"agent returned {len(generated_quiz.quiz_items)} item(s)")

        for i, item in enumerate(generated_quiz.quiz_items):
            print(item)
            print(f"  item {i}: question={item.question[:60]!r}, "
                  f"answer_count={len(item.answer)}")

        QUESTION_TYPE_MAP = {
            "single choice question": "SQ",
            "multiple choice question": "MCQ",
        }

        LETTER_TO_INDEX = {"A": 0, "B": 1, "C": 2, "D": 3}

        skipped = 0

        for item in generated_quiz.quiz_items:
            if len(item.options) != 4:
                skipped += 1
                continue

            correct_index = LETTER_TO_INDEX[item.answer]

            question = Question.objects.create(
                quiz=quiz,
                question_text=item.question,
                question_type=QUESTION_TYPE_MAP.get(item.question_type.value, "SQ"),
                topic=quiz.quiz_topic,
                explanation=item.explanation,
                creator=quiz.creator,
                hint=item.hint,
            )
            for i, option_text in enumerate(item.options):
                Answer.objects.create(
                    question=question,
                    answer_text=option_text,
                    is_correct=(i == correct_index),
                    is_option=True,
                )

        if quiz.questions.count() == 0:
            raise ValueError(
                f"Agent produced {len(generated_quiz.quiz_items)} question(s), "
                f"all unusable (skipped: {skipped}). No questions were saved."
            )

        quiz.status = "READY"
        quiz.save(update_fields=["status"])

    except SoftTimeLimitExceeded:
        quiz.status = "FAILED"
        quiz.error_message = "Generation took too long and was stopped. Try a shorter document or fewer questions."
        quiz.save(update_fields=["status", "error_message"])
        raise

    except Exception as e:
        quiz.status = "FAILED"
        quiz.error_message = str(e)
        quiz.save(update_fields=["status", "error_message"])
        raise

    finally:
        # Not storing the pdf after processing
        if pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)

