from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END
from .agents.agent_nodes import (
    creator_agent, evaluator_agent, correction_agent, safety_check_agent,
    guardrail_agent, structure_node,
)
from .agents.routing import (
    route_after_guardrail, route_after_structural_check,
    route_after_evaluator, route_after_safety_check,
)
from .schema import State
import mlflow


mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("quiz-generation")
mlflow.langchain.autolog()

workflow = StateGraph(State)
workflow.add_node("creator_agent", creator_agent)
workflow.add_node("evaluator_agent", evaluator_agent)
workflow.add_node("corrector_agent", correction_agent)
workflow.add_node("safety_agent", safety_check_agent)
workflow.add_node("guardrail_agent", guardrail_agent)
workflow.add_node("structural_check_node", structure_node)
workflow.add_edge(START, "guardrail_agent")
workflow.add_edge("creator_agent", "structural_check_node")
workflow.add_edge("corrector_agent", "evaluator_agent")

workflow.add_conditional_edges(
    "guardrail_agent", route_after_guardrail, ["creator_agent", END]
)
workflow.add_conditional_edges(
    "structural_check_node", route_after_structural_check, ["safety_agent", "creator_agent", END]
)
workflow.add_conditional_edges(
    "safety_agent", route_after_safety_check, ["evaluator_agent", END]
)
workflow.add_conditional_edges(
    "evaluator_agent", route_after_evaluator, ["corrector_agent", "creator_agent", END]
)

memory = InMemorySaver()
graph = workflow.compile(checkpointer=memory)