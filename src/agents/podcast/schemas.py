from typing import Literal

from pydantic import BaseModel, Field

Section = Literal["opening", "introduction", "topic_intro", "deep_dive", "wrap_up", "conclusion", "outro"]  # Sections of the episode, in order
QuestionType = Literal[
    "open",          # a broad open question
    "follow_up",     # digs deeper into a previous answer
    "informational",
    "challenge",     # pushes back / presents a counter-angle
    "clarification", # asks for a clarification or a concrete example
    "personal",      # the guest's personal connection to the topic
    "summary",       # wrap-up / looking ahead
]


class TopicBrief(BaseModel):
    topic: str = Field(description="The episode topic, one focused sentence, in Hebrew")
    angle: str = Field(description="The narrative angle or hook that makes this episode compelling, in Hebrew")
    arc_beats: list[str] = Field(description="3-5 ordered beats of the episode's narrative arc, each in Hebrew")
    target_minutes: int = Field(description="Target episode length in minutes")


class Persona(BaseModel):
    name: str = Field(description="The character's full name, in Hebrew")
    role: str = Field(description="Short label for what this person does on the show or in their field, in Hebrew")
    backstory: str = Field(description="Short biography grounding the character's credibility, in Hebrew")
    connection_to_topic: str = Field(description="Why this character cares about or is an authority on the topic, in Hebrew")
    speaking_style: str = Field(description="Speech mannerisms and tone, used to keep dialogue lines in character, in Hebrew")
    gender: Literal["male", "female"] = Field(description="Used for TTS voice casting")


class PodcastCast(BaseModel):
    hosts: list[Persona] = Field(description="1-2 interviewers")
    guest: Persona = Field(description="The single interviewee")


class LineupItem(BaseModel):
    index: int = Field(description="0-based position of this item in the episode order")
    section: Section = Field(description="Which part of the episode this item belongs to")
    question: str = Field(description="The question the host will ask, in Hebrew")
    question_type: QuestionType = Field(description="The conversational function of this question")
    goal: str = Field(description="What this item should achieve for the listener, in Hebrew")
    search_queries: list[str] = Field(description="2-4 retrieval queries for finding supporting material in the user's sources; Hebrew or the sources' language")


class Lineup(BaseModel):
    items: list[LineupItem] = Field(description="The episode's lineup items, in speaking order")


class ResearchNoteContent(BaseModel):
    context_digest: str = Field(description="Focused summary of what the sources say about this item's question")
    key_facts: list[str] = Field(description="Specific facts, numbers, and quotes worth using in the dialogue")
    citations: list[str] = Field(description="Source references backing the digest, in the store's citation format")


class ResearchNote(ResearchNoteContent):
    item_index: int = Field(description="Index of the lineup item this note supports")
