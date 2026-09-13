import mlflow
from ..schema import (
    Quiz, GuardrailCheck, QuizEvaluation, CorrectionOutput,
    FeedbackItem, SafetyCheck, State,
)
from ..prompts import (
    correction_prompt, creator_prompt, safety_check_prompt,
    evaluator_prompt, guardrail_prompt, EXAMPLE_QUIZ_ITEM,
    structural_retry_block_prompt, evaluation_retry_block_prompt, general_creator_prompt,
    ai_ml_creator_prompt, ai_ml_example_item, interview_prep_creator_prompt,
    grade_12_below_creator_prompt, general_example_item, interview_prep_example_item,
    grade_12_below_example_item,
)
from ..llms import (
    safety_llm, guardrail_llm, evaluator_llm,
    creator_llm, corrector_llm, moderation_client,
)

CREATOR_PROMPT_MAP = {
    "UPSC": (creator_prompt, EXAMPLE_QUIZ_ITEM),
    "GENERAL": (general_creator_prompt, general_example_item),
    "AI_ML": (ai_ml_creator_prompt, ai_ml_example_item),
    "INTERVIEW_PREP": (interview_prep_creator_prompt, interview_prep_example_item),
    "GRADE_12_BELOW": (grade_12_below_creator_prompt, grade_12_below_example_item),
}

def check_moderation(user_input: str) -> tuple[bool, str]:
    """Returns (flagged, comma-separated list of triggered categories)."""
    result = moderation_client.moderations.create(
        model="omni-moderation-latest",
        input=user_input,
    )
    result_data = result.results[0]
    if not result_data.flagged:
        return False, ""

    triggered = [
        category for category, is_flagged in result_data.categories.model_dump().items()
        if is_flagged
    ]
    return True, ", ".join(triggered)


def guardrail_agent(state: State) -> dict:
    source_text = state["source_text"]
    tips = state["quiz_details"].tips_for_quiz_creation
    description = state["quiz_details"].description

    is_flagged, triggered_categories = check_moderation(f"{description}\n{tips}")
    if is_flagged:
        return {
            "guardrail_passed": False,
            "guardrail_reason": f"Flagged by moderation filter: {triggered_categories}.",
            "guardrail_category": "profanity",
        }

    guardrail = guardrail_llm.with_structured_output(GuardrailCheck)
    prompt = guardrail_prompt.invoke({
        "tips_for_quiz_creation": tips,
        "description": description,
        "source_text": source_text,
    })
    guardrail_response = guardrail.invoke(prompt)

    return {
        "guardrail_passed": guardrail_response.passed,
        "guardrail_reason": guardrail_response.reason,
        "guardrail_category": guardrail_response.category,
        "end_reason": "guardrail_blocked" if not guardrail_response.passed else None,
    }


def creator_agent(state: State) -> dict:
    source_text = state["source_text"]
    quiz_details = state["quiz_details"]
    retry_reason = state.get("retry_reason", "")
    token_budget = 800 * quiz_details.max_questions + 400
    prompt_template, example_item = CREATOR_PROMPT_MAP.get(
        quiz_details.exam_name, CREATOR_PROMPT_MAP["GENERAL"]
    )


    if retry_reason == "structural":
        retry_feedback = state.get("retry_feedback", "")
        retry_block = structural_retry_block_prompt.format(retry_feedback=retry_feedback)
    elif retry_reason == "evaluation":
        whole_quiz_items = [
            fi for fi in state.get("evaluation_feedback_items", [])
            if not fi.indices
        ]
        retry_feedback = " ".join(fi.note for fi in whole_quiz_items)
        retry_block = evaluation_retry_block_prompt.format(retry_feedback=retry_feedback)
    else:
        retry_block = ""

    # creator = creator_llm.with_structured_output(Quiz)
    creator = creator_llm.bind(max_tokens=token_budget).with_structured_output(Quiz)
    prompt = prompt_template.invoke({
        "quiz_topic": quiz_details.quiz_topic,
        "exam_name": quiz_details.exam_name,
        "difficulty": quiz_details.difficulty,
        "description": quiz_details.description,
        "tips_for_quiz_creation": quiz_details.tips_for_quiz_creation,
        "max_questions": quiz_details.max_questions,
        "example_quiz_item": example_item,
        "source_text": source_text,
        "retry_block": retry_block,
    })
    creator_response = creator.invoke(prompt)
    generated_quiz = creator_response

    return {
        "generated_quiz": generated_quiz
    }


def evaluator_agent(state: State) -> dict:
    generated_quiz = state["generated_quiz"]
    quiz_details = state["quiz_details"]
    token_budget = 800 * quiz_details.max_questions + 400
    source_text = state["source_text"]
    eval_attempts = state.get("evaluator_attempts", 0)
    # evaluator = llm.with_structured_output(QuizEvaluation)
    evaluator = evaluator_llm.bind(max_tokens=token_budget).with_structured_output(QuizEvaluation)
    prompt = evaluator_prompt.invoke({
        "quiz_topic": quiz_details.quiz_topic,
        "exam_name": quiz_details.exam_name,
        "difficulty": quiz_details.difficulty,
        "description": quiz_details.description,
        "tips_for_quiz_creation": quiz_details.tips_for_quiz_creation,
        "questionnaire": generated_quiz.model_dump_json(indent=2),
        "source_text": source_text,
    })

    evaluator_response = evaluator.invoke(prompt)

    if evaluator_response.status == "APPROVED":
        return {
            "evaluation_status": evaluator_response.status,
            "evaluator_attempts": 1,
            "evaluation_feedback_items": [],
            "end_reason": "approved",
        }
    else:
        return {
            "evaluation_status": evaluator_response.status,
            "evaluator_attempts": 1,
            "evaluation_feedback_items": evaluator_response.feedback_items,
            "retry_reason": "evaluation",
            "end_reason": "evaluator attempts exhausted" if eval_attempts + 1 >= 2 else None,
        }


def correction_agent(state: State) -> dict:
    generated_quiz = state["generated_quiz"]
    source_text = state["source_text"]

    feedback_items = [
        FeedbackItem(**item) if isinstance(item, dict) else item
        for item in state["evaluation_feedback_items"]
    ]

    targeted_items = [feed_item for feed_item in feedback_items if feed_item.indices]
    flagged_indices = sorted({item for feed_item in targeted_items for item in feed_item.indices})
    flagged_questions = {
        i: generated_quiz.quiz_items[i].model_dump() for i in flagged_indices
    }
    all_question_topics = {
        i: item.question for i, item in enumerate(generated_quiz.quiz_items)
    }
    correction_token_budget = 800 * len(flagged_indices) + 1000

    prompt = correction_prompt.invoke({
        "feedback_items": targeted_items,
        "flagged_questions": flagged_questions,
        "all_question_topics": all_question_topics,
        "source_text": source_text,
    })
    corrector = corrector_llm.bind(max_tokens=correction_token_budget).with_structured_output(CorrectionOutput)
    corrector_response = corrector.invoke(prompt)

    for correction in corrector_response.corrections:
        index = correction.index
        generated_quiz.quiz_items[index] = correction.corrected_item

    return {
        "generated_quiz": generated_quiz,
        "correction_occurred": 1,
    }


def safety_check_agent(state: State) -> dict:
    generated_quiz = state["generated_quiz"]
    # source_text = state["source_text"]
    citations_only = "\n\n".join(
        f"[Question {i} citation]: {item.source_citation}"
        for i, item in enumerate(generated_quiz.quiz_items)
    )

    safety_check_llm = safety_llm.with_structured_output(SafetyCheck)
    prompt = safety_check_prompt.invoke({
        "questionnaire": generated_quiz.model_dump_json(indent=2),
        "source_text": citations_only,
    })
    safety_response = safety_check_llm.invoke(prompt)

    return {
        "safety_passed": safety_response.passed,
        "safety_reason": safety_response.reason,
        "safety_category": safety_response.category,
        "end_reason": "safety check failed" if not safety_response.passed else None,
    }


@mlflow.trace(name="structural_check")
def structure_node(state: State) -> dict:
    generated_quiz = state["generated_quiz"].quiz_items
    quiz_details = state["quiz_details"]
    structural_attempts = state.get("structural_attempts", 0)
    leaked_reasoning_phrases = ["let me think", "the answer should be", "wait, actually"]
    feedback = []
    structural_error = False
    # Length check
    if quiz_details.max_questions != len(generated_quiz):
        feedback.append("Generated quiz questions are not the same as requested by the User.")
        structural_error = True

    for quiz_item in generated_quiz:
        if ("\n" in quiz_item.hint or "\n" in quiz_item.explanation
                or any("\n" in option for option in quiz_item.options)):
            feedback.append("Embedded newlines in the item")
            structural_error = True
            break

    for quiz_item in generated_quiz:
        found_leaked_reasoning = False
        for phrase in leaked_reasoning_phrases:
            if phrase in quiz_item.question or phrase in quiz_item.hint or phrase in quiz_item.explanation:
                feedback.append("Leaked Reasoning in the generated quiz.")
                structural_error = True
                found_leaked_reasoning = True
                break
        if found_leaked_reasoning:
            break

    question_texts = set(quiz_item.question for quiz_item in generated_quiz)
    if len(question_texts) != len(generated_quiz):
        feedback.append("Duplicate Questions are present in the generated quiz.")
        structural_error = True

    if structural_error:
        span = mlflow.get_current_active_span()
        span.set_attributes({
            "structural_failure_reason": " ".join(feedback),
            "structural_attempt_number": structural_attempts + 1,
        })
        return {
            "structural_check_passed": False,
            "retry_reason": "structural",
            "retry_feedback": " ".join(feedback),
            "structural_attempts": 1,
            "end_reason": "structural checks exhausted" if structural_attempts + 1 >= 2 else None,
        }

    return {
        "structural_check_passed": True,
        "structural_attempts": 1,
    }