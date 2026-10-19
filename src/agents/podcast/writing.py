from typing import Literal

from agents.podcast.format_utils import (
    count_words_he,
    format_cast,
    format_recent_turns,
    format_research,
)
from agents.podcast.models import get_model
from agents.podcast.prompts import WRITE_SEGMENT_SYSTEM, WRITE_SEGMENT_USER
from agents.podcast.schemas import SegmentScript
from agents.podcast.state import PodcastState

WORDS_PER_MINUTE_HE = (
    140  # rough spoken-Hebrew pace; tune against real generated episodes
)

SECTION_WEIGHTS = {
    "opening": 0.3,
    "introduction": 0.6,
    "topic_intro": 0.8,
    "deep_dive": 1.2,
    "wrap_up": 0.8,
    "conclusion": 0.5,
    "outro": 0.3,
}
MIN_SEGMENT_WORDS = 15


def compute_word_budget(item, remaining_items, target_minutes: int, words_used_so_far: int) -> int:
    """
    Word budget for one lineup item, redistributing whatever is LEFT of the
    episode's total word budget across the items not yet written — weighted
    by section. A segment that overran eats into what's left for the rest
    of the episode; one that ran short frees up room for later ones. This
    keeps the running total self-correcting toward target_minutes instead
    of each item getting a fixed share regardless of what already happened.
    """
    total_words = target_minutes * WORDS_PER_MINUTE_HE
    remaining_words = max(total_words - words_used_so_far, 0)
    remaining_weight = sum(SECTION_WEIGHTS[i.section] for i in remaining_items)
    if remaining_weight == 0:
        return MIN_SEGMENT_WORDS
    share = SECTION_WEIGHTS[item.section] / remaining_weight
    return max(round(remaining_words * share), MIN_SEGMENT_WORDS)


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

    words_used_so_far = sum(count_words_he(turn.text_he) for turn in existing_turns)
    remaining_items = lineup[segment_index:]
    word_budget = compute_word_budget(
        item, remaining_items, state["brief"].target_minutes, words_used_so_far
    )

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
            word_budget=word_budget,
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

    # Safety net: the prompt does most of the work; trim whole turns from the
    # end only when a segment blows well past its budget.
    actual_words = sum(count_words_he(turn.text_he) for turn in normalized_turns)
    if actual_words > word_budget * 1.5:
        kept = []
        running_words = 0
        for turn in normalized_turns:
            words = count_words_he(turn.text_he)
            if kept and running_words + words > word_budget * 1.5:
                break
            kept.append(turn)
            running_words += words
        print(
            f"[podcast] segment {item.index} ({item.section}) exceeded its word "
            f"budget ({actual_words} > {word_budget}); trimmed to "
            f"{len(kept)}/{len(normalized_turns)} turns"
        )
        normalized_turns = kept

    return {
        "turns": existing_turns + normalized_turns,
        "running_summary": segment.updated_summary,
        "current_segment": segment_index + 1,
    }


def next_or_done(state: PodcastState) -> Literal["write_segment", "done"]:
    if state["current_segment"] < len(state["lineup"]):
        return "write_segment"
    return "done"
