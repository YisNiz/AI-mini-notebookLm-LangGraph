from agents.podcast.schemas import PodcastCast


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
