from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import StateGraph, START, END
from .agents.agent_nodes import (
    creator_agent, evaluator_agent, correction_agent, safety_check_agent,
    guardrail_agent, structure_node,
)
from .agents.routing import (
    route_after_guardrail, route_after_structural_check,
    route_after_evaluator, route_after_safety_check,
)
from .agents.digest_nodes import filter_digest_agent, relevance_filter_agent, summarize_and_evaluate_agent

from .schema import State, DigestState
import mlflow
import os
from dotenv import load_dotenv
from urllib.parse import quote_plus
import atexit


load_dotenv()
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
os.environ["MLFLOW_ENABLE_ASYNC_TRACE_LOGGING"] = "false"
DB_URI = (
    f"postgresql://{quote_plus(os.getenv('DB_USER'))}:{quote_plus(os.getenv('DB_PASSWORD'))}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)

_mlflow_ready = False
_connection_pool = None
_checkpointer = None
_graph = None
_digest_graph = None


def _ensure_mlflow():
    global _mlflow_ready
    if _mlflow_ready:
        return
    try:
        mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:8080"))
        mlflow.set_experiment("quiz-generation")
        mlflow.langchain.autolog()
    except Exception as e:
        print(f"[workflow.py] MLflow setup failed, tracing disabled for this process: {e}")
    _mlflow_ready = True


def get_connection_pool():
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = ConnectionPool(
            conninfo=DB_URI,
            max_size=10,
            kwargs={"autocommit": True, "row_factory": None},
        )
        atexit.register(_connection_pool.close)
    return _connection_pool


def get_checkpointer():
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = PostgresSaver(get_connection_pool())
        _checkpointer.setup()
    return _checkpointer


def get_graph():
    global _graph
    if _graph is not None:
        return _graph

    _ensure_mlflow()

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

    _graph = workflow.compile(checkpointer=get_checkpointer())
    return _graph


def get_digest_graph():
    global _digest_graph
    if _digest_graph is not None:
        return _digest_graph

    digest_workflow = StateGraph(DigestState)
    digest_workflow.add_node("filter_digest_agent", filter_digest_agent)
    digest_workflow.add_node("relevance_filter_agent", relevance_filter_agent)
    digest_workflow.add_node("summarize_and_evaluate_agent", summarize_and_evaluate_agent)

    digest_workflow.set_entry_point("filter_digest_agent")
    digest_workflow.add_edge("filter_digest_agent", "relevance_filter_agent")
    digest_workflow.add_edge("relevance_filter_agent", "summarize_and_evaluate_agent")
    digest_workflow.add_edge("summarize_and_evaluate_agent", END)

    _digest_graph = digest_workflow.compile()
    return _digest_graph