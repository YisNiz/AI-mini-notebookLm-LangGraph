from typing import TypedDict

from agents.podcast.schemas import LineupItem, PodcastCast, TopicBrief


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
