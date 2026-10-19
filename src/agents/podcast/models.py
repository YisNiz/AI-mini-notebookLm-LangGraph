from functools import lru_cache

from langchain.chat_models import init_chat_model

MODELS = {
    "planning": "anthropic:claude-haiku-5-5",   # plan_topic, design_personas, plan_lineup
    "context": "anthropic:claude-haiku-5-5",    # gather_context
    "writing": "anthropic:claude-sonnet-5-5",   # write_segment
}


@lru_cache
def get_model(role: str):
    return init_chat_model(MODELS[role])
