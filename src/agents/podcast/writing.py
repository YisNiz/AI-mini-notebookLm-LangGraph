from typing import Literal

from agents.podcast.format_utils import format_cast, format_recent_turns, format_research
from agents.podcast.models import get_model
from agents.podcast.prompts import WRITE_SEGMENT_SYSTEM, WRITE_SEGMENT_USER
from agents.podcast.schemas import SegmentScript
from agents.podcast.state import PodcastState


def write_segment(state: PodcastState) -> dict:
    """Write dialogue for one lineup item and advance the writing loop."""
    segment_index = state.get("current_segment", 0)
    lineup = state["lineup"]

    if segment_index >= len(lineup):
        raise ValueError("No lineup item remains to be written.")

    item = lineup[segment_index]
    existing_turns = state.get("turns", [])

    research = [
        note for note in state.get("research", []) if note.item_index == item.index
    ]

    next_turn_index = len(existing_turns)

    llm = get_model("writing").with_structured_output(SegmentScript, method="json_schema")
    segment = llm.invoke([
        {"role": "system", "content": WRITE_SEGMENT_SYSTEM},
        {"role": "user", "content": WRITE_SEGMENT_USER.format(
            topic=state["brief"].topic,
            angle=state["brief"].angle,
            arc_beats="\n".join(f"- {beat}" for beat in state["brief"].arc_beats),
            cast=format_cast(state["cast"]),
            section=item.section,
            question=item.question,
            question_type=item.question_type,
            goal=item.goal,
            research=format_research(research),
            running_summary=state.get(
                "running_summary", "This is the first segment; there is no previous summary yet."
            ),
            recent_turns=format_recent_turns(existing_turns[-6:]),
        )},
    ])

    if not segment.turns:
        raise ValueError(f"The model returned no dialogue turns for lineup item {item.index}")

    normalized_turns = [
        turn.model_copy(update={"turn_index": next_turn_index + offset})
        for offset, turn in enumerate(segment.turns)
    ]

    return {
        "turns": existing_turns + normalized_turns,
        "running_summary": segment.updated_summary,
        "current_segment": segment_index + 1,
    }


def next_or_done(state: PodcastState) -> Literal["write_segment", "done"]:
    if state["current_segment"] < len(state["lineup"]):
        return "write_segment"
    return "done"
