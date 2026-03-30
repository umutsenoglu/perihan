"""Shared helper for building LLM clients from trainer config / env vars."""

import os
from openai import OpenAI


def build_client(provider: str) -> OpenAI:
    """Build an OpenAI-compatible client for the given provider."""
    if provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        return OpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=api_key,
        )
    # Default: Ollama
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    return OpenAI(base_url=f"{ollama_host}/v1", api_key="ollama")


def get_model_from_env(role: str, default_model: str = "phi4:14b", default_provider: str = "ollama"):
    """Read model config from env vars set by steps.py.

    Returns (model_name, provider, client).
    """
    env_prefix = f"TRAINER_{role.upper()}"
    model = os.environ.get(f"{env_prefix}_MODEL", "") or default_model
    provider = os.environ.get(f"{env_prefix}_PROVIDER", "") or default_provider
    client = build_client(provider)
    return model, provider, client
