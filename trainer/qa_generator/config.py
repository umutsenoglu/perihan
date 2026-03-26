"""QA Generator configuration."""

from pathlib import Path

# Paths
COLLECTOR_OUTPUT_DIR = Path(__file__).parent.parent / "collector" / "output"
QA_OUTPUT_DIR = Path(__file__).parent / "output"
QA_STATE_FILE = QA_OUTPUT_DIR / "qa_state.json"
QA_OUTPUT_FILE = QA_OUTPUT_DIR / "qa_output.json"
MANIFEST_FILE = COLLECTOR_OUTPUT_DIR / "manifest.json"

# Package size limit (bytes) — stay well under Gemini's ~4 MB input limit
MAX_PACKAGE_BYTES = 3 * 1024 * 1024  # 3 MB

# QA counts per package
QA_PER_SINGLE_DOC = 5       # strategy 1: search questions from one doc
QA_PER_SAME_CATEGORY = 10   # strategy 2: reasoning questions from same category
QA_PER_CROSS_STORYLINE = 10 # strategy 3: multi-doc questions across categories

# Strategy weights (how often each strategy is picked)
STRATEGY_WEIGHTS = {
    "single_doc": 40,
    "same_category": 30,
    "cross_storyline": 30,
}

# Batch settings
BATCH_INTERVAL = 10  # seconds between packages
