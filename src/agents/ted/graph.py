from langgraph.graph import StateGraph, START, END

from agents.ted.nodes import plan_talk
from agents.ted.state import TedState


def build_ted_graph():
    builder = StateGraph(TedState)
    builder.add_node("plan_talk", plan_talk)

    builder.add_edge(START, "plan_talk")
    builder.add_edge("plan_talk", END)

    return builder.compile()
