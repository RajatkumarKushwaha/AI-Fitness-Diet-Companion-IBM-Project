"""Scientifically-standard health & fitness calculations.

Every formula here follows a published reference:

* BMI      — WHO classification of body mass index
* BMR      — Mifflin-St Jeor equation (1990), the most accurate
             predictive equation for resting energy expenditure
* TDEE     — BMR x Harris-Benedict activity multiplier
* Energy   — 1 g protein = 4 kcal, 1 g carbohydrate = 4 kcal, 1 g fat = 9 kcal
* Water    — ~35 ml per kg of body weight per day (EFSA general guidance)
"""

# Activity multipliers (Harris-Benedict activity factors)
ACTIVITY_LEVELS = {
    "Sedentary (desk job, no exercise)": 1.20,
    "Lightly Active (1-3 days/week)": 1.375,
    "Moderately Active (3-5 days/week)": 1.55,
    "Very Active (6-7 days/week)": 1.725,
    "Athlete (training twice a day)": 1.90,
}

# Daily calorie adjustment applied on top of TDEE, per goal
GOAL_ADJUSTMENTS = {
    "Fat Loss": -500,             # ~0.5 kg of fat per week
    "Aggressive Fat Loss": -750,  # ~0.75 kg of fat per week
    "Maintain Weight": 0,
    "Lean Muscle Gain": 250,      # small, clean surplus
    "Clean Bulk": 500,            # ~0.25-0.5 kg per week
}

# Mifflin-St Jeor gender constants ("Other" uses the mean of both)
_GENDER_OFFSET = {"Male": 5, "Female": -161, "Other": -78}

# Safe minimum daily calories (general clinical guidance)
_MIN_CALORIES = {"Male": 1500, "Female": 1200, "Other": 1200}

# WHO BMI categories: (upper_limit, label, emoji, hex_color)
BMI_CATEGORIES = [
    (18.5, "Underweight", "🟡", "#eab308"),
    (25.0, "Normal Weight", "🟢", "#22c55e"),
    (30.0, "Overweight", "🟠", "#f97316"),
    (float("inf"), "Obese", "🔴", "#ef4444"),
]

# WHO expert consultation (2004) BMI cut-offs for Asian populations
BMI_CATEGORIES_ASIAN = [
    (18.5, "Underweight", "🟡", "#eab308"),
    (23.0, "Normal Weight", "🟢", "#22c55e"),
    (25.0, "Overweight", "🟠", "#f97316"),
    (float("inf"), "Obese", "🔴", "#ef4444"),
]


def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    """Body Mass Index = weight (kg) / height (m)^2."""
    if height_cm <= 0:
        raise ValueError("Height must be greater than zero.")
    height_m = height_cm / 100
    return round(weight_kg / (height_m ** 2), 1)


def bmi_category(bmi: float, asian: bool = False) -> tuple:
    """Return (label, emoji, color) for a BMI value.

    Set ``asian=True`` to use the lower WHO cut-offs recommended for
    Asian populations (relevant for Indian users).
    """
    table = BMI_CATEGORIES_ASIAN if asian else BMI_CATEGORIES
    for upper, label, emoji, color in table:
        if bmi < upper:
            return label, emoji, color
    return table[-1][1], table[-1][2], table[-1][3]


def calculate_bmr(weight_kg: float, height_cm: float, age: int, gender: str) -> int:
    """Basal Metabolic Rate via the Mifflin-St Jeor equation (kcal/day)."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return int(round(base + _GENDER_OFFSET.get(gender, -78)))


def calculate_tdee(bmr: int, activity_label: str) -> int:
    """Total Daily Energy Expenditure = BMR x activity multiplier."""
    multiplier = ACTIVITY_LEVELS.get(activity_label, 1.20)
    return int(round(bmr * multiplier))


def calculate_target_calories(tdee: int, goal: str, gender: str) -> int:
    """Daily calorie target for a goal, never below the safe minimum."""
    target = tdee + GOAL_ADJUSTMENTS.get(goal, 0)
    return max(target, _MIN_CALORIES.get(gender, 1200))


def calculate_macros(weight_kg: float, target_calories: int, goal: str) -> dict:
    """Split the daily calorie target into protein / carbs / fats (grams).

    Protein is set per kg of body weight (sport-nutrition range 1.8-2.2 g/kg),
    fats at ~28% of total energy, and carbohydrates take the remainder.
    """
    if goal in ("Lean Muscle Gain", "Clean Bulk"):
        protein_g = round(2.0 * weight_kg)   # higher protein for muscle building
    else:
        protein_g = round(1.8 * weight_kg)   # fat loss / maintenance

    protein_kcal = protein_g * 4
    fats_kcal = round(target_calories * 0.28)
    fats_g = round(fats_kcal / 9)
    carbs_kcal = target_calories - protein_kcal - fats_kcal
    carbs_g = max(round(carbs_kcal / 4), 0)

    return {
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fats_g": fats_g,
        "protein_kcal": protein_kcal,
        "carbs_kcal": carbs_g * 4,
        "fats_kcal": fats_g * 9,
    }


def calculate_water_intake_ml(weight_kg: float) -> int:
    """Daily water target: ~35 ml per kg of body weight."""
    return int(round(weight_kg * 35))


def healthy_weight_range(height_cm: float) -> tuple:
    """Weight range (kg) that keeps BMI inside the WHO healthy band 18.5-24.9."""
    h = height_cm / 100
    return round(18.5 * h * h, 1), round(24.9 * h * h, 1)
