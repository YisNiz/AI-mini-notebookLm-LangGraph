from langgraph.graph import StateGraph, START, END

from agents.ted.nodes import plan_talk, gather_context, write_talk
from agents.ted.state import TedState


def build_ted_graph():
    builder = StateGraph(TedState)
    builder.add_node("plan_talk", plan_talk)
    builder.add_node("gather_context", gather_context)
    builder.add_node("write_talk", write_talk)

    builder.add_edge(START, "plan_talk")
    builder.add_edge("plan_talk", "gather_context")
    builder.add_edge("gather_context", "write_talk")
    builder.add_edge("write_talk", END)

    return builder.compile()
