from typing import Literal

from agents.podcast.format_utils import count_words_he, format_cast, format_full_script
from agents.podcast.models import get_model
from agents.podcast.prompts import (
    CRITIQUE_SCRIPT_SYSTEM,
    CRITIQUE_SCRIPT_USER,
    REVISE_SCRIPT_SYSTEM,
    REVISE_SCRIPT_USER,
)
from agents.podcast.schemas import CritiqueResult, RevisedTurns
from agents.podcast.state import PodcastState
from agents.podcast.nodes.writing import WORDS_PER_MINUTE_HE

MAX_REVISIONS = 2
LENGTH_TOLERANCE = 1.15


def critique_script(state: PodcastState) -> dict:
    """
    Step 6: Review the complete script as a whole — catching cross-segment
    issues (repetition, broken continuity, pacing) no single write_segment
    call could see, and enforcing the episode's total length as a fact
    computed in code rather than trusting the model's own judgment of it.
    """
    brief = state["brief"]
    turns = state["turns"]

    target_words = brief.target_minutes * WORDS_PER_MINUTE_HE
    actual_words = sum(count_words_he(turn.text_he) for turn in turns)
    overage_percent = round((actual_words / target_words - 1) * 100) if target_words else 0

    llm = get_model("critique").with_structured_output(CritiqueResult, method="json_schema")
    critique = llm.invoke([
        {"role": "system", "content": CRITIQUE_SCRIPT_SYSTEM},
        {
            "role": "user",
            "content": CRITIQUE_SCRIPT_USER.format(
                topic=brief.topic,
                angle=brief.angle,
                arc_beats="\n".join(f"- {beat}" for beat in brief.arc_beats),
                target_minutes=brief.target_minutes,
                cast=format_cast(state["cast"]),
                actual_words=actual_words,
                target_words=target_words,
                words_per_minute=WORDS_PER_MINUTE_HE,
                overage_percent=overage_percent,
                full_script=format_full_script(turns),
            ),
        },
    ])

    if target_words and actual_words > target_words * LENGTH_TOLERANCE and critique.approved:
        print(
            f"[podcast] critique approved a script that is {overage_percent}% over "
            f"target ({actual_words} > {target_words}); overriding to not-approved"
        )
        critique = critique.model_copy(update={"approved": False})

    return {"critique": critique}


def critique_next(state: PodcastState) -> Literal["revise_script", "done"]:
    critique = state.get("critique")
    revision_count = state.get("revision_count", 0)

    if critique is not None and critique.approved:
        return "done"
    if revision_count >= MAX_REVISIONS:
        print(f"[podcast] hit MAX_REVISIONS ({MAX_REVISIONS}) without approval; shipping as-is")
        return "done"
    return "revise_script"


def revise_script(state: PodcastState) -> dict:
    """
    Step 7: Rewrite the full script to address the editor's issues, then
    loop back through critique_script for re-review.
    """
    brief = state["brief"]
    critique = state["critique"]

    llm = get_model("critique").with_structured_output(RevisedTurns, method="json_schema")
    revised = llm.invoke([
        {"role": "system", "content": REVISE_SCRIPT_SYSTEM},
        {"role": "user", "content": REVISE_SCRIPT_USER.format(
            topic=brief.topic,
            angle=brief.angle,
            arc_beats="\n".join(f"- {beat}" for beat in brief.arc_beats),
            target_minutes=brief.target_minutes,
            cast=format_cast(state["cast"]),
            issues="\n".join(f"- {issue}" for issue in critique.issues),
            full_script=format_full_script(state["turns"]),
        )},
    ])

    if not revised.turns:
        raise ValueError("Revision returned no turns; refusing to discard the previous script.")

    normalized_turns = [
        turn.model_copy(update={"turn_index": i})
        for i, turn in enumerate(revised.turns)
    ]

    return {
        "turns": normalized_turns,
        "revision_count": state.get("revision_count", 0) + 1,
    }
