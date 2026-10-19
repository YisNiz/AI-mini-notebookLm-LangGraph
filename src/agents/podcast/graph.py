from langgraph.graph import StateGraph, START, END

from agents.podcast.planning import design_personas, plan_lineup, plan_topic
from agents.podcast.state import PodcastState


def build_podcast_graph():
    builder = StateGraph(PodcastState)
    builder.add_node("plan_topic", plan_topic)
    builder.add_node("design_personas", design_personas)
    builder.add_node("plan_lineup", plan_lineup)

    builder.add_edge(START, "plan_topic")
    builder.add_edge("plan_topic", "design_personas")
    builder.add_edge("design_personas", "plan_lineup")
    builder.add_edge("plan_lineup", END)

    return builder.compile()
