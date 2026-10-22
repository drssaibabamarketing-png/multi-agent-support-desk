"""Central settings for the Support Response Desk (Milestone 3)."""
import os
from pathlib import Path

BASE = Path(__file__).parent
REVIEWS_CSV = BASE / "data" / "reviews.csv"
OUT = BASE / "outputs"
LOGS = BASE / "logs"

PRODUCT = "Groww"
AMC = "HDFC Mutual Fund"

# Date the corpus snapshot was last verified against the live pages.
# UPDATE THIS when you re-verify corpus_registry.py (or set CORPUS_LAST_CHECKED in the env).
CORPUS_LAST_CHECKED = os.environ.get("CORPUS_LAST_CHECKED", "22 Oct 2026")

# --- Pattern agent
PATTERN_WINDOW_DAYS = 28        # total window, anchored on the newest review in the CSV
PATTERN_SPLIT_DAYS = 14         # recent half vs previous half -> trend
SIM_THRESHOLD = 0.15            # cosine similarity for "same issue" reviews (calibrated on 40 sampled 1-2 star reviews)
MIN_RECURRING = 5               # fewer similar reviews than this in the window = one-off
RISING_RATIO = 1.5              # recent >= 1.5x previous (and >= MIN_RECURRING) = rising
HOT_RECENT = 10                 # recurring with this many in the recent half also triggers HOLD

# --- Orchestrator / reviewer
MAX_SENTENCES = 3
MAX_REWORK = 1                  # reviewer -> orchestrator rounds
MAX_REFINEMENTS = 5

# --- Optional LLM (Groq). Everything works without it; with it, the orchestrator
# rewrites the draft and the reviewer adds an LLM advice-judge on top of the rules.
USE_LLM = bool(os.environ.get("GROQ_API_KEY")) and os.environ.get("USE_LLM", "1") != "0"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
