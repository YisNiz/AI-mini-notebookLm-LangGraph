import re

from agents.podcast.schemas import PodcastCast, ResearchNote

_AUDIO_TAG_RE = re.compile(r"\[[^\]]{1,40}\]\s*")


def strip_audio_tags(text: str) -> str:
    """Remove ElevenLabs v3 delivery tags like [thoughtful] for user-facing display."""
    return _AUDIO_TAG_RE.sub("", text).strip()


def count_words_he(text: str) -> int:
    """Count spoken words in a Hebrew turn, excluding audio delivery tags."""
    return len(strip_audio_tags(text).split())


def format_cast(cast: PodcastCast) -> str:
    lines = []
    for i, host in enumerate(cast.hosts, 1):
        label = "Host" if len(cast.hosts) == 1 else f"Host {i}"
        lines.append(
            f"{label}: {host.name} ({host.gender}) — {host.role}\n"
            f"  speaking_style: {host.speaking_style}\n"
            f"  connection_to_topic: {host.connection_to_topic}"
        )
    g = cast.guest
    lines.append(
        f"Guest: {g.name} ({g.gender}) — {g.role}\n"
        f"  backstory: {g.backstory}\n"
        f"  speaking_style: {g.speaking_style}\n"
        f"  connection_to_topic: {g.connection_to_topic}"
    )
    return "\n\n".join(lines)


def format_research(notes: list[ResearchNote]) -> str:
    if not notes:
        return "No research note exists for this lineup item."

    blocks = []
    for note in notes:
        facts = (
            "\n".join(f"- {fact}" for fact in note.key_facts)
            or "- No concrete facts were retrieved."
        )
        citations = ", ".join(note.citations) or "No citations"
        blocks.append(
            f"Digest:\n{note.context_digest}\n\n"
            f"Key facts:\n{facts}\n\n"
            f"Citations: {citations}"
        )
    return "\n\n---\n\n".join(blocks)


def format_recent_turns(turns: list) -> str:
    if not turns:
        return "No previous dialogue turns."
    return "\n".join(f"{turn.speaker_name}: {turn.text_he}" for turn in turns)


def format_full_script(turns: list) -> str:
    """Render the whole script with turn_index, so the critic can point at exact turns."""
    if not turns:
        return "No turns."
    return "\n".join(
        f"[{turn.turn_index}] {turn.speaker_name}: {turn.text_he}"
        for turn in turns
    )
