from agents.podcast.format_utils import format_cast
from agents.podcast.models import get_model
from agents.podcast.prompts import (
    DESIGN_PERSONAS_SYSTEM, DESIGN_PERSONAS_USER,
    PLAN_LINEUP_SYSTEM, PLAN_LINEUP_USER,
    PLAN_TOPIC_SYSTEM, PLAN_TOPIC_USER,
)
from agents.podcast.schemas import Lineup, PodcastCast, TopicBrief
from agents.podcast.state import PodcastState

from core.store import store
from core.sources import build_sources_overview


def plan_topic(state: PodcastState):
    """Step 1: Plan the episode topic and narrative arc."""
    overview = build_sources_overview(store)
    if not overview.strip():
        raise ValueError(
            "No active sources to plan a podcast from. Enable at least one source first."
        )
    llm = get_model("planning").with_structured_output(TopicBrief, method="json_schema")
    brief = llm.invoke([
        {"role": "system", "content": PLAN_TOPIC_SYSTEM},
        {"role": "user", "content": PLAN_TOPIC_USER.format(source_overview=overview)},
    ])
    return {"source_overview": overview, "brief": brief}


def design_personas(state: PodcastState):
    """Step 2: Design the podcast cast (hosts and guest)."""
    brief = state["brief"]
    llm = get_model("planning").with_structured_output(PodcastCast, method="json_schema")
    cast = llm.invoke([
        {"role": "system", "content": DESIGN_PERSONAS_SYSTEM},
        {"role": "user", "content": DESIGN_PERSONAS_USER.format(
            topic=brief.topic,
            angle=brief.angle,
            arc_beats="\n".join(brief.arc_beats),
            target_minutes=brief.target_minutes,
        )},
    ])
    return {"cast": cast}


def plan_lineup(state: PodcastState):
    """Step 3: Plan the episode lineup (questions and structure)."""
    brief = state["brief"]
    llm = get_model("planning").with_structured_output(Lineup, method="json_schema")
    lineup = llm.invoke([
        {"role": "system", "content": PLAN_LINEUP_SYSTEM},
        {"role": "user", "content": PLAN_LINEUP_USER.format(
            topic=brief.topic,
            angle=brief.angle,
            arc_beats="\n".join(brief.arc_beats),
            target_minutes=brief.target_minutes,
            cast=format_cast(state["cast"]),
        )},
    ])
    # Positions are the source of truth; don't trust model-generated indexes.
    items = [
        item.model_copy(update={"index": i})
        for i, item in enumerate(lineup.items)
    ]
    return {"lineup": items}
