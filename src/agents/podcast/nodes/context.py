from langgraph.types import Send

from core.store import store
from core.sources import format_docs
from agents.podcast.models import get_model
from agents.podcast.prompts import GATHER_CONTEXT_SYSTEM, GATHER_CONTEXT_USER
from agents.podcast.schemas import ResearchNote, ResearchNoteContent
from agents.podcast.state import GatherInput, PodcastState


def fan_out(state: PodcastState) -> list[Send]:
    """Step 4: Route each lineup item that requires source material
    to a separate gather_context invocation."""
    sends = [
        Send("gather_context", {"item": item, "brief": state["brief"]})
        for item in state["lineup"]
        if item.search_queries
    ]
    if not sends:
        # No item needs retrieval (the model ignored the lineup instructions);
        # skip straight to writing instead of silently dead-ending the graph.
        return [Send("write_segment", dict(state))]
    return sends


def gather_context(state: GatherInput) -> dict:
    """Retrieve source passages and prepare a research note for one lineup item."""
    item = state["item"]
    brief = state["brief"]

    docs = []
    seen_contents = set()

    for query in item.search_queries:
        results = store.search(query, k=4)
        for doc in results:
            if doc.page_content in seen_contents:
                continue
            seen_contents.add(doc.page_content)
            docs.append(doc)

    if not docs:
        # Nothing retrieved — report the gap directly instead of forcing the
        # model to fill required fields from empty passages.
        return {
            "research": [
                ResearchNote(
                    item_index=item.index,
                    context_digest="לא נמצאו קטעים רלוונטיים במקורות לשאלה זו.",
                    key_facts=[],
                    citations=[],
                )
            ]
        }

    context_blocks = format_docs(docs)

    llm = get_model("context").with_structured_output(ResearchNoteContent, method="json_schema")
    content = llm.invoke([
        {"role": "system", "content": GATHER_CONTEXT_SYSTEM},
        {"role": "user", "content": GATHER_CONTEXT_USER.format(
            topic=brief.topic,
            angle=brief.angle,
            question=item.question,
            goal=item.goal,
            context_blocks=context_blocks,
        )},
    ])

    note = ResearchNote(item_index=item.index, **content.model_dump())
    return {"research": [note]}
