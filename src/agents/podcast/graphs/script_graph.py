from langgraph.graph import StateGraph, START, END

from agents.podcast.nodes.context import fan_out, gather_context
from agents.podcast.nodes.critique import critique_next, critique_script, revise_script
from agents.podcast.nodes.planning import design_personas, plan_lineup, plan_topic
from agents.podcast.nodes.writing import next_or_done, write_segment
from agents.podcast.state import PodcastState


def build_script_graph():
    builder = StateGraph(PodcastState)
    builder.add_node("plan_topic", plan_topic)
    builder.add_node("design_personas", design_personas)
    builder.add_node("plan_lineup", plan_lineup)
    builder.add_node("gather_context", gather_context)
    builder.add_node("write_segment", write_segment)
    builder.add_node("critique_script", critique_script)
    builder.add_node("revise_script", revise_script)

    builder.add_edge(START, "plan_topic")
    builder.add_edge("plan_topic", "design_personas")
    builder.add_edge("design_personas", "plan_lineup")
    builder.add_conditional_edges("plan_lineup", fan_out, ["gather_context", "write_segment"])
    builder.add_edge("gather_context", "write_segment")
    builder.add_conditional_edges(
        "write_segment", next_or_done, {"write_segment": "write_segment", "done": "critique_script"}
    )
    builder.add_conditional_edges(
        "critique_script", critique_next, {"revise_script": "revise_script", "done": END}
    )
    builder.add_edge("revise_script", "critique_script")

    return builder.compile()
