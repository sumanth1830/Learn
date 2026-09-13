import json

import mlflow
# from models import QuizGenerationLog
#
# log = QuizGenerationLog.objects.last()
trace_id = "tr-8a66e74fc2bdc27a30cf8242d5b353fa"
print("Using trace_id:", trace_id)
mlflow.set_tracking_uri(
    "sqlite:////Users/merlin/PycharmProjects/Learn/personalmanager/mlflow.db"
)
# trace = mlflow.get_trace(trace_id=trace_id, flush=True)
print(mlflow.get_tracking_uri())
# traces = mlflow.search_traces(max_results=10)
#
# print("type:", type(traces))
# print("shape:", getattr(traces, "shape", None))
# print("columns:", getattr(traces, "columns", None))
# print("value:")
# print(traces)

trace_id = "tr-f06ddfa76a54aeabb1bb35f22250762e"
# traces = mlflow.search_traces(max_results=10)
trace = mlflow.get_trace(trace_id=trace_id, flush=True)
trace_dict = trace.data.to_dict()  # alternative: trace.to_dict() depending on MLflow version

# 2. Convert the dictionary to a JSON string
with open(f"trace_{trace_id}.json", "w") as f:
    json.dump(trace.data.to_dict(), f, indent=4)
# trace_json = json.dumps(trace_dict, indent=4)

# print(trace_json)

# print(type(trace))
# print(trace)
# for span in trace.data.spans:
#     print(span.name)
#     print(span.attributes)
#     print()
#
# traces = mlflow.search_traces(
#     max_results=20,
#     flush=True,
# )
#
# print(traces[["trace_id", "request_time", "state"]])
# trace_id = "tr-23e1f77bd4cf45a284c4535c68bddbbe"
# trace = mlflow.get_trace(
#     trace_id=trace_id,
#     flush=True,
# )

# print("TRACE:", trace)
#
# for span in trace.data.spans:
#     print("\nSPAN:", span.name)
#     print("ATTRIBUTES:", span.attributes)
#
#     if span.name == "ChatOpenAI":
#         print("\n=== COST ===")
#         print(span.get_attribute("mlflow.llm.cost"))

# Get the most recent trace
# last_trace_id = mlflow.get_last_active_trace_id()
# trace = mlflow.get_trace(trace_id=last_trace_id)

# Access token usage and cost for each LLM call
# print("== Token usage and cost for each LLM call: ==")
# for span in trace.data.spans:
#     usage = span.get_attribute("mlflow.chat.tokenUsage")
#     cost = span.llm_cost
#     print(dir(span))
#     print("start:", getattr(span, "start_time_ns", None))
#     print("end:", getattr(span, "end_time_ns", None))
#     print(f"{span.name}:")
#     if usage:
#         print(f"  Input tokens: {usage['input_tokens']}")
#         print(f"  Output tokens: {usage['output_tokens']}")
#         print(f"  Total tokens: {usage['total_tokens']}")
#     if cost:
#         print(f"  Input cost: ${cost['input_cost']:.6f}")
#         print(f"  Output cost: ${cost['output_cost']:.6f}")
#         print(f"  Total cost: ${cost['total_cost']:.6f}")