# LLM Usage Map

Where and how Perihan calls an LLM.

## User-facing (parametric model)

The user selects the model from the Settings UI. These calls use whatever model is active.

| # | File | What it does |
|---|------|-------------|
| 1 | `perihan-core/.../chat_service.py` | RAG query — main chat response |
| 2 | `perihan-core/.../chat_service.py` | MCP tool-calling loop — agentic fallback |
| 3 | `perihan-app/.../routers/chat.py` | Folder-scoped chat — `/chat-folder` endpoint |

## Internal (hardcoded model)

### gemini-2.5-flash (via OpenAI-compatible client)

| # | File | What it does |
|---|------|-------------|
| 4 | `perihan-app/.../routers/index.py` | File summary generation during indexing |

### Configurable from TheLoop UI (default: phi4:14b / Ollama)

Model selection is in TheLoop dashboard > Model Config panel. Config stored in `trainer/trainer_config.json`.
Env vars (`TRAINER_<ROLE>_MODEL`, `TRAINER_<ROLE>_PROVIDER`) are passed to subprocesses by `steps.py`.

| # | Role | File | What it does |
|---|------|------|-------------|
| 5 | benchmark | `trainer/eval_runner/runner.py` | Benchmark — sends question + raw docs to LLM |
| 6 | judge | `trainer/eval_runner/runner.py` | Judge — scores responses |
| 7 | qa_generator | `trainer/qa_generator/generator.py` | QA generation — creates test questions from docs |
| 8 | collector | `trainer/collector/generators/base.py` | Synthetic data generation — creates training content |

## Model pricing

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|----------------------|
| gemini-3.0-flash | $0.50 | $3.00 |
| gemini-2.5-flash | $0.30 | $2.50 |
| gemini-2.5-flash-lite | $0.10 | $0.40 |
| gemini-2.0-flash | $0.15 | $0.60 |
