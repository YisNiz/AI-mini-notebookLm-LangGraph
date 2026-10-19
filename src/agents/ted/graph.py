from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy

from agents.ted.nodes import (
    plan_talk, gather_context, write_talk, count_words,
    critique_script, revise, after_critique, approval, after_approval,
    synthesize_audio,
)
from agents.ted.state import TedState


def build_ted_graph(checkpointer=None):
    builder = StateGraph(TedState)
    builder.add_node("plan_talk", plan_talk)
    builder.add_node("gather_context", gather_context)
    builder.add_node("write_talk", write_talk)
    builder.add_node("count_words", count_words)
    builder.add_node("critique_script", critique_script)
    builder.add_node("revise", revise)
    builder.add_node("approval", approval)
    builder.add_node(
        "synthesize_audio", synthesize_audio, retry_policy=RetryPolicy(max_attempts=3)
    )

    builder.add_edge(START, "plan_talk")
    builder.add_edge("plan_talk", "gather_context")
    builder.add_edge("gather_context", "write_talk")
    builder.add_edge("write_talk", "count_words")
    builder.add_edge("count_words", "critique_script")
    builder.add_conditional_edges(
        "critique_script", after_critique, {"approval": "approval", "revise": "revise"}
    )
    builder.add_edge("revise", "count_words")
    builder.add_conditional_edges(
        "approval", after_approval, {"revise": "revise", "synthesize_audio": "synthesize_audio"}
    )
    builder.add_edge("synthesize_audio", END)

    return builder.compile(checkpointer=checkpointer)


def build_ted_graph_for_server():
    """Zero-arg factory for langgraph dev/Studio, which injects values into any
    recognized parameter (e.g. checkpointer) and provides its own persistence."""
    return build_ted_graph()
