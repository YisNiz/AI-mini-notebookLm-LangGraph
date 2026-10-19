def run(job_id: str = "test") -> dict:
    """Run the script graph end to end (planning → research → writing → critique
    loop) and return the final state. Imported lazily for the same reason as
    agents.ted: entry points must finish their setup (.env, NetFree SSL) before
    core.store opens its API clients."""
    from agents.podcast.graphs.script_graph import build_script_graph

    graph = build_script_graph()
    final_state = None
    for mode, chunk in graph.stream(
        {"job_id": job_id},
        config={
            "recursion_limit": 60,
            "max_concurrency": 2,
            "run_name": "podcast-script",
            "metadata": {"job_id": job_id},
        },
        stream_mode=["updates", "values"],
    ):
        if mode == "updates":
            for node in chunk:
                print(f">>> {node} done")
        else:
            final_state = chunk
    return final_state
