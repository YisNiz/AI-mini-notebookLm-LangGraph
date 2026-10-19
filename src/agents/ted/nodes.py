import re

from agents.ted.models import get_model
from agents.ted.prompts import (
    PLAN_TALK_SYSTEM,
    PLAN_TALK_USER,
    WRITE_TALK_SYSTEM,
    WRITE_TALK_USER,
)
from agents.ted.schemas import TalkBrief
from agents.ted.state import HARD_CAP, TARGET_WORDS, WORD_MAX, WORD_MIN, TedState

from core.store import store
from core.sources import build_sources_overview, format_docs


def plan_talk(state: TedState) -> dict:
    """LLM: plan the talk (topic, hook, 3 key points) from the source summaries."""
    overview = build_sources_overview(store)
    if not overview.strip():
        raise ValueError("No active sources to plan a talk from. Enable at least one source first.")

    llm = get_model("planning").with_structured_output(TalkBrief)
    brief = llm.invoke([
        {"role": "system", "content": PLAN_TALK_SYSTEM},
        {"role": "user", "content": PLAN_TALK_USER.format(source_overview=overview)},
    ])
    return {"brief": brief, "revision_count": 0}


def gather_context(state: TedState) -> dict:
    """No LLM here: retrieve source passages for each key point of the brief."""
    docs, seen = [], set()
    for point in state["brief"].key_points:
        for doc in store.search(point, k=4):
            if doc.page_content not in seen:
                seen.add(doc.page_content)
                docs.append(doc)

    context = format_docs(docs) if docs else "No relevant passages were found in the sources."
    return {"context": context}


def write_talk(state: TedState) -> dict:
    """LLM: write the full Hebrew script, with the word budget stated in the prompt."""
    brief = state["brief"]
    llm = get_model("writing")
    response = llm.invoke([
        {
            "role": "system",
            "content": WRITE_TALK_SYSTEM.format(
                target_words=TARGET_WORDS, word_min=WORD_MIN, word_max=WORD_MAX
            ),
        },
        {
            "role": "user",
            "content": WRITE_TALK_USER.format(
                topic=brief.topic,
                hook=brief.hook,
                key_points="\n".join(f"- {p}" for p in brief.key_points),
                context=state["context"],
            ),
        },
    ])
    return {"script_he": response.text.strip()}


def _sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+", text.strip())


def count_words(state: TedState) -> dict:
    """Pure code: count the script's words; hard-trim at a sentence boundary
    if the model overshot HARD_CAP. The prompt asks for the budget — this node
    enforces it."""
    script = state["script_he"]
    if len(script.split()) <= HARD_CAP:
        return {"word_count": len(script.split())}

    kept, used = [], 0
    for sentence in _sentences(script):
        n = len(sentence.split())
        if kept and used + n > HARD_CAP:
            break
        kept.append(sentence)
        used += n
    trimmed = " ".join(kept)
    return {"script_he": trimmed, "word_count": len(trimmed.split())}
