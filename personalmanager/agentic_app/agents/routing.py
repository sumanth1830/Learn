from langgraph.graph import END
from ..schema import State


def route_after_structural_check(state: State) -> str:
    if state["structural_check_passed"]:
        return "safety_agent"
    if state.get("structural_attempts", 0) >= 2:
        return END  # exhausted - hard fail
    return "creator_agent"  # retry

def route_after_guardrail(state: State) -> str:
    if state["guardrail_passed"]:
        return "creator_agent"
    else:
        return END

def route_after_safety_check(state: State) -> str:
    if state["safety_passed"]:
        return "evaluator_agent"
    else:
        return END

def route_after_evaluator(state: State) -> str:
    if state["evaluation_status"] == "APPROVED" or state.get("evaluator_attempts", 0) >= 2:
        return END

    # Dealing with [], no indices whole quiz feedback loop
    has_whole_quiz_feedback = any(
        not fi.indices for fi in state.get("evaluation_feedback_items", [])
    )
    if has_whole_quiz_feedback:
        return "creator_agent"
    return "corrector_agent"