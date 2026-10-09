"""Application configuration and constants for FitAI.

Everything app-wide that is not business logic lives here, so the UI
(main.py) and the engine stay clean and easy to maintain.
"""

from pathlib import Path

# ----------------------------------------------------------------- paths ---
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"

# ------------------------------------------------------------ app identity ---
APP_NAME = "FitAI"
APP_TAGLINE = "Smart Health & Diet Companion"
APP_ICON = "💪"

# ------------------------------------------------------------- form options ---
GENDERS = ["Male", "Female", "Other"]

GOALS = [
    "Fat Loss",
    "Aggressive Fat Loss",
    "Maintain Weight",
    "Lean Muscle Gain",
    "Clean Bulk",
]

DIET_PREFERENCES = ["Vegetarian", "Non-Vegetarian", "Vegan", "Keto"]

# ------------------------------------------------------------- nav pages ---
PAGES = [
    "🏠 Dashboard",
    "🍽️ Meal Plan",
    "🏋️ Workout Plan",
    "📈 Progress",
    "🤖 AI Coach",
]
