import operator
from typing import Annotated, TypedDict

from agents.podcast.schemas import DialogueTurn, LineupItem, PodcastCast, ResearchNote, TopicBrief


class PodcastState(TypedDict, total=False):
    # input
    job_id: str
    # step 1 — plan_topic
    source_overview: str
    brief: TopicBrief
    # step 2 — design_personas
    cast: PodcastCast
    # step 3 — plan_lineup
    lineup: list[LineupItem]
    # step 4 — gather_context (parallel branches append, never overwrite)
    research: Annotated[list[ResearchNote], operator.add]
    # step 5 — write_segment loop (sequential: each iteration returns the full list)
    current_segment: int
    turns: list[DialogueTurn]
    running_summary: str


class GatherInput(TypedDict):
    item: LineupItem
    brief: TopicBrief
