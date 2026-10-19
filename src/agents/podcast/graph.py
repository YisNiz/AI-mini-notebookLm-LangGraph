from langgraph.graph import StateGraph, START, END

from agents.podcast.context import fan_out, gather_context
from agents.podcast.planning import design_personas, plan_lineup, plan_topic
from agents.podcast.state import PodcastState
from agents.podcast.writing import next_or_done, write_segment


def build_podcast_graph():
    builder = StateGraph(PodcastState)
    builder.add_node("plan_topic", plan_topic)
    builder.add_node("design_personas", design_personas)
    builder.add_node("plan_lineup", plan_lineup)
    builder.add_node("gather_context", gather_context)
    builder.add_node("write_segment", write_segment)

    builder.add_edge(START, "plan_topic")
    builder.add_edge("plan_topic", "design_personas")
    builder.add_edge("design_personas", "plan_lineup")
    builder.add_conditional_edges("plan_lineup", fan_out, ["gather_context", "write_segment"])
    builder.add_edge("gather_context", "write_segment")
    builder.add_conditional_edges(
        "write_segment", next_or_done, {"write_segment": "write_segment", "done": END}
    )

    return builder.compile()
