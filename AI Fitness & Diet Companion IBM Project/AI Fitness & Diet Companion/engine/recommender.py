"""The FitAI recommendation engine — a fully local, rule-based "AI coach".

No API keys, no cloud calls, no fake progress bars. The engine:

1. Analyses the user's biometrics with standard scientific formulas
   (see ``utils/calculations.py``).
2. Builds a 7-day meal plan matched to the calorie target, macro split
   and diet preference, using the curated meal database.
3. Builds a 7-day workout blueprint matched to the fitness goal.
4. Generates personalised coaching tips.
5. Powers the "AI Coach" chat with intent-based answers about the plan.
"""

from collections import Counter
from dataclasses import dataclass, field

from utils.calculations import (
    bmi_category,
    calculate_bmi,
    calculate_bmr,
    calculate_macros,
    calculate_target_calories,
    calculate_tdee,
    calculate_water_intake_ml,
    healthy_weight_range,
)
from utils.database import EXERCISE_BY_ID, MEALS, is_compatible

# Daily calorie distribution across meal slots (must sum to 1.0)
MEAL_SLOTS = [
    ("Breakfast", 0.25),
    ("Lunch", 0.35),
    ("Dinner", 0.30),
    ("Snack", 0.05),
    ("Snack", 0.05),
]

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday",
             "Friday", "Saturday", "Sunday"]

# ~7700 kcal of deficit/surplus ≈ 1 kg of body weight change
_KCAL_PER_KG = 7700


# ------------------------------------------------------------------ models ---
@dataclass
class UserProfile:
    """Everything the engine needs to know about the user."""
    name: str
    age: int
    gender: str
    weight_kg: float
    height_cm: float
    activity: str
    goal: str
    diet: str


@dataclass
class HealthAnalysis:
    """Computed health metrics and daily targets."""
    bmi: float
    bmi_category: str
    bmi_emoji: str
    bmi_color: str
    bmi_category_asian: str
    bmr: int
    tdee: int
    target_calories: int
    macros: dict
    water_ml: int
    healthy_weight_min: float
    healthy_weight_max: float
    weight_to_healthy_mid: float
    weekly_change_kg: float


# ------------------------------------------------------------------ engine ---
class FitnessEngine:
    """Turns a :class:`UserProfile` into a complete personalised plan."""

    def __init__(self, profile: UserProfile):
        self.profile = profile
        self.analysis = self._analyze()

    # ------------------------------------------------------------ analysis ---
    def _analyze(self) -> HealthAnalysis:
        p = self.profile
        bmi = calculate_bmi(p.weight_kg, p.height_cm)
        cat, emoji, color = bmi_category(bmi)
        cat_asian, _, _ = bmi_category(bmi, asian=True)
        bmr = calculate_bmr(p.weight_kg, p.height_cm, p.age, p.gender)
        tdee = calculate_tdee(bmr, p.activity)
        target = calculate_target_calories(tdee, p.goal, p.gender)
        macros = calculate_macros(p.weight_kg, target, p.goal)
        w_min, w_max = healthy_weight_range(p.height_cm)
        mid = round((w_min + w_max) / 2, 1)
        weekly = round((target - tdee) * 7 / _KCAL_PER_KG, 2)
        return HealthAnalysis(
            bmi=bmi,
            bmi_category=cat,
            bmi_emoji=emoji,
            bmi_color=color,
            bmi_category_asian=cat_asian,
            bmr=bmr,
            tdee=tdee,
            target_calories=target,
            macros=macros,
            water_ml=calculate_water_intake_ml(p.weight_kg),
            healthy_weight_min=w_min,
            healthy_weight_max=w_max,
            weight_to_healthy_mid=round(p.weight_kg - mid, 1),
            weekly_change_kg=weekly,
        )

    # ----------------------------------------------------------- meal plan ---
    @staticmethod
    def _pick_meal(pool: list, target_kcal: float, avoid_ids: set) -> dict:
        """Pick the best meal for a slot.

        Among meals within ±25% of the slot's calorie target, the one with
        the highest protein wins (protein is the hardest macro to hit on
        vegetarian/vegan diets); ties break on calorie closeness. If nothing
        is in range, fall back to the closest match.
        """
        candidates = [m for m in pool if m["id"] not in avoid_ids] or pool
        in_range = [m for m in candidates
                    if abs(m["kcal"] - target_kcal) <= 0.25 * target_kcal]
        if in_range:
            return max(in_range,
                       key=lambda m: (m["protein"], -abs(m["kcal"] - target_kcal)))
        return min(candidates, key=lambda m: abs(m["kcal"] - target_kcal))

    @staticmethod
    def _scale_to_target(meal: dict, slot_target: float,
                         lo: float = 0.75, hi: float = 2.0) -> dict:
        """Return a copy of the meal with a portion size scaled to the target.

        Like a real coach prescribing portions: a bulking plan gets 1.5×
        portions, a fat-loss plan slightly smaller ones. The scale is clamped
        to a realistic range and rounded to the nearest quarter portion.
        """
        scale = slot_target / meal["kcal"]
        scale = max(lo, min(hi, round(scale * 4) / 4))
        scaled = dict(meal)
        if scale != 1.0:
            scaled["kcal"] = round(meal["kcal"] * scale)
            scaled["protein"] = round(meal["protein"] * scale)
            scaled["carbs"] = round(meal["carbs"] * scale)
            scaled["fats"] = round(meal["fats"] * scale)
        scaled["portion"] = f"{scale}×"
        scaled["portion_scale"] = scale
        return scaled

    def _build_topup(self, gap: int) -> dict:
        """Build a protein top-up item (e.g. a shake) sized to the protein gap.

        Like a real coach: if whole-food meals cannot reach the protein
        target, the plan includes an explicit, diet-appropriate supplement.
        """
        diet = self.profile.diet
        servings = 2 if gap >= 40 else 1
        if diet == "Vegan":
            base = {"name": "Plant Protein Shake (scoop in water)",
                    "per": {"kcal": 110, "protein": 20, "carbs": 3, "fats": 2},
                    "ingredients": ["Plant protein powder", "Water / ice"]}
        elif diet == "Keto":
            base = {"name": "Whey Isolate Shake (scoop in water)",
                    "per": {"kcal": 110, "protein": 25, "carbs": 1, "fats": 1},
                    "ingredients": ["Whey isolate", "Water / ice"]}
        else:
            base = {"name": "Whey Protein Shake (scoop in water)",
                    "per": {"kcal": 120, "protein": 24, "carbs": 3, "fats": 1},
                    "ingredients": ["Whey protein", "Water / ice"]}
        per = base["per"]
        return {
            "id": f"topup-{diet.lower()}-{servings}",
            "name": f"{base['name']} ×{servings}" if servings > 1 else base["name"],
            "meal_type": "Top-up",
            "tags": [diet] if diet != "Non-Vegetarian" else ["Vegetarian"],
            "kcal": per["kcal"] * servings,
            "protein": per["protein"] * servings,
            "carbs": per["carbs"] * servings,
            "fats": per["fats"] * servings,
            "prep_min": 2,
            "portion": f"{servings} scoop" + ("s" if servings > 1 else ""),
            "portion_scale": 1.0,
            "ingredients": base["ingredients"],
        }

    def build_meal_plan(self, days: int = 7) -> list:
        """Build a varied N-day meal plan matched to the calorie & protein targets.

        1. Main meals (breakfast / lunch / dinner) are picked per slot share
           and portion-scaled to the slot target.
        2. The two snacks absorb whatever calories remain, so each day lands
           close to the daily calorie target.
        3. If the meals still fall short of the protein target, a
           diet-appropriate protein top-up (e.g. a shake) is added to the
           plan and the snacks are shrunk to keep calories on target.
        """
        target = self.analysis.target_calories
        protein_target = self.analysis.macros["protein_g"]
        plan = []
        recent: dict = {slot: [] for slot, _ in MEAL_SLOTS}

        for d in range(days):
            day_meals: dict = {}

            def choose(slot: str, slot_target: float,
                       lo: float = 0.75, hi: float = 2.0) -> dict:
                pool = [m for m in MEALS
                        if m["meal_type"] == slot
                        and is_compatible(m, self.profile.diet)]
                if not pool:
                    # Extremely restrictive diet: fall back to any meal of the
                    # slot rather than failing — better than no plan at all.
                    pool = [m for m in MEALS if m["meal_type"] == slot]
                avoid = set(recent[slot][-2:])      # vary meals across days
                chosen = self._pick_meal(pool, slot_target, avoid)
                chosen = self._scale_to_target(chosen, slot_target, lo, hi)
                recent[slot].append(chosen["id"])
                return chosen

            # --- main meals: fixed share of the daily target ---
            mains_kcal = 0
            for slot, share in MEAL_SLOTS:
                if slot == "Snack":
                    continue
                chosen = choose(slot, target * share)
                day_meals[slot] = [chosen]
                mains_kcal += chosen["kcal"]

            # --- snacks: absorb the remaining calories ---
            remaining = max(target - mains_kcal, 0.05 * target)
            per_snack = remaining / 2
            day_meals["Snacks"] = [choose("Snack", per_snack, lo=0.5, hi=2.5)
                                   for _ in range(2)]

            def day_totals() -> dict:
                all_meals = [m for meals in day_meals.values() for m in meals]
                return {key: sum(m[key] for m in all_meals)
                        for key in ("kcal", "protein", "carbs", "fats")}

            totals = day_totals()

            # --- protein top-up, sized to the actual gap ---
            gap = protein_target - totals["protein"]
            if gap >= 12:
                topup = self._build_topup(gap)
                day_meals["Top-up"] = [topup]
                # Keep the day on its calorie target: make room for the
                # top-up by shrinking the snacks — or, if there is too little
                # room left for a meaningful snack, dropping them entirely.
                allowed = target - mains_kcal - topup["kcal"]
                snacks = day_meals["Snacks"]
                snack_kcal = sum(m["kcal"] for m in snacks)
                if allowed < max(90, 0.05 * target):
                    day_meals["Snacks"] = []
                elif snack_kcal > allowed:
                    factor = max(0.5, allowed / snack_kcal)
                    for snack in snacks:
                        snack["kcal"] = round(snack["kcal"] * factor)
                        snack["protein"] = round(snack["protein"] * factor)
                        snack["carbs"] = round(snack["carbs"] * factor)
                        snack["fats"] = round(snack["fats"] * factor)
                        snack["portion_scale"] = round(
                            snack["portion_scale"] * factor, 2)
                        snack["portion"] = f"{snack['portion_scale']}×"
                totals = day_totals()

            plan.append({
                "day": DAY_NAMES[d % len(DAY_NAMES)],
                "meals": day_meals,
                "totals": totals,
            })
        return plan

    def grocery_list(self, meal_plan: list) -> Counter:
        """Aggregate ingredients across the whole plan for a shopping list."""
        counter: Counter = Counter()
        for day in meal_plan:
            for meals in day["meals"].values():
                for meal in meals:
                    for ingredient in meal["ingredients"]:
                        counter[ingredient] += 1
        return counter

    # -------------------------------------------------------- workout plan ---
    def build_workout_plan(self) -> list:
        """Build a 7-day workout blueprint matched to the fitness goal."""
        goal = self.profile.goal

        if goal in ("Fat Loss", "Aggressive Fat Loss"):
            template = [
                ("Monday", "Full-Body Strength A",
                 ["push-ups", "goblet-squat", "bent-over-row", "glute-bridge", "plank"], 55,
                 "Compound moves to keep muscle while burning fat."),
                ("Tuesday", "HIIT Cardio",
                 ["jumping-jacks", "burpees", "mountain-climbers", "high-knees", "jump-rope"], 30,
                 "Short, intense intervals to spike calorie burn."),
                ("Wednesday", "Full-Body Strength B",
                 ["walking-lunges", "bent-over-row", "tricep-dips", "goblet-squat", "leg-raises"], 55,
                 "Hit the muscles from new angles."),
                ("Thursday", "Active Recovery",
                 ["brisk-walk", "cat-cow", "worlds-greatest-stretch", "foam-rolling"], 25,
                 "Keep the blood flowing — recovery is where progress happens."),
                ("Friday", "HIIT + Core",
                 ["burpees", "mountain-climbers", "bicycle-crunches", "plank", "leg-raises"], 35,
                 "Finish the week with a metabolic burner."),
                ("Saturday", "Full-Body Circuit",
                 ["box-step-ups", "push-ups", "goblet-squat", "burpees", "plank"], 40,
                 "One circuit, 3–4 rounds, minimal rest."),
                ("Sunday", "Rest", [], 0,
                 "Complete rest or gentle stretching. Sleep 7–9 hours."),
            ]
        elif goal in ("Lean Muscle Gain", "Clean Bulk"):
            template = [
                ("Monday", "Push (Chest / Shoulders / Triceps)",
                 ["bench-press", "incline-dumbbell-press", "overhead-press", "tricep-dips", "push-ups"], 60,
                 "Add weight when you hit the top of every rep range."),
                ("Tuesday", "Pull (Back / Biceps)",
                 ["bent-over-row", "lat-pulldown", "face-pulls", "bicep-curls"], 60,
                 "Squeeze at the top of every rep."),
                ("Wednesday", "Legs",
                 ["goblet-squat", "bulgarian-split-squat", "romanian-deadlift", "glute-bridge"], 60,
                 "Train legs hard — they drive whole-body growth."),
                ("Thursday", "Rest", [], 0,
                 "Rest or light mobility work."),
                ("Friday", "Upper Body",
                 ["bench-press", "bent-over-row", "overhead-press", "bicep-curls", "tricep-dips"], 55,
                 "Volume day for chest, back and arms."),
                ("Saturday", "Lower Body",
                 ["goblet-squat", "romanian-deadlift", "bulgarian-split-squat",
                  "walking-lunges", "glute-bridge"], 60,
                 "Add a set or 2.5 kg if last week felt easy."),
                ("Sunday", "Rest", [], 0,
                 "Complete rest. Prioritise protein and sleep."),
            ]
        else:  # Maintain Weight
            template = [
                ("Monday", "Full-Body Strength",
                 ["goblet-squat", "push-ups", "bent-over-row", "glute-bridge", "plank"], 45,
                 "Quality over quantity."),
                ("Tuesday", "Steady-State Cardio",
                 ["brisk-walk", "jump-rope"], 35,
                 "Easy pace — you should be able to hold a conversation."),
                ("Wednesday", "Rest", [], 0,
                 "Rest or yoga."),
                ("Thursday", "Full-Body Strength",
                 ["walking-lunges", "overhead-press", "tricep-dips", "leg-raises", "plank"], 45,
                 "Focus on form, not ego."),
                ("Friday", "Cardio & Mobility",
                 ["cycling", "cat-cow", "worlds-greatest-stretch", "foam-rolling"], 35,
                 "Move for 30–40 minutes at an easy pace."),
                ("Saturday", "Active Leisure",
                 ["brisk-walk", "jump-rope"], 40,
                 "Sport, hiking, swimming — anything fun counts."),
                ("Sunday", "Rest", [], 0,
                 "Full recovery."),
            ]

        plan = []
        for day, focus, ex_ids, duration, note in template:
            exercises = [EXERCISE_BY_ID[eid] for eid in ex_ids]
            plan.append({
                "day": day,
                "focus": focus,
                "exercises": exercises,
                "duration_min": duration,
                "est_kcal": sum(e["kcal"] for e in exercises),
                "note": note,
            })
        return plan

    # -------------------------------------------------------- coaching tips ---
    def coaching_tips(self) -> list:
        """Personalised, actionable tips based on the analysis."""
        a = self.analysis
        p = self.profile
        m = a.macros
        tips = []

        if a.bmi >= 25:
            tips.append(
                f"Your BMI is {a.bmi} ({a.bmi_category}). A sustained 500 kcal/day deficit "
                f"typically yields ~0.5 kg of fat loss per week — slow and steady wins.")
        elif a.bmi < 18.5:
            tips.append(
                f"Your BMI is {a.bmi} ({a.bmi_category}). Focus on a small calorie surplus "
                f"plus strength training to build healthy mass.")
        else:
            tips.append(
                f"Your BMI is {a.bmi} — right inside the healthy band. Your job now is "
                f"consistency: keep training and eating around your target.")

        tips.append(
            f"Aim for ~{m['protein_g']} g of protein daily "
            f"(≈{round(m['protein_g'] / max(p.weight_kg, 1), 1)} g per kg body weight) "
            f"to protect and build muscle.")
        tips.append(
            f"Drink about {a.water_ml / 1000:.1f} L of water a day — more on training days.")

        if "Loss" in p.goal:
            tips.append(
                "Fat loss is 80% kitchen, 20% gym. Weigh yourself once a week — "
                "same day, same time, after waking up.")
        elif "Gain" in p.goal or "Bulk" in p.goal:
            tips.append(
                "To build muscle you need a small surplus, progressive overload in the gym "
                "and 7–9 hours of sleep — muscle is built while you rest.")
        else:
            tips.append(
                "Maintenance is a skill too: hit your calories, train 3–4× a week and "
                "your weight will stay stable without effort.")

        tips.append(
            "Put protein on your plate at every meal — it keeps you full for hours "
            "and protects muscle while dieting.")
        tips.append(
            "Missed a workout? Just show up the next day. Consistency beats intensity, "
            "every single time.")
        return tips


# ------------------------------------------------------------- AI coach chat ---
def _protein_sources(diet: str) -> str:
    if diet == "Vegan":
        return ("tofu, tempeh, lentils (dal), chickpeas, kidney beans (rajma), "
                "soya chunks, quinoa and plant protein powder.")
    if diet == "Vegetarian":
        return ("paneer, Greek yogurt, milk, lentils (dal), chickpeas, soya chunks "
                "and whey protein.")
    if diet == "Keto":
        return ("eggs, paneer, chicken, fish, Greek yogurt and whey protein — "
                "while keeping carbs under ~30–50 g/day.")
    return ("chicken breast, fish, eggs, paneer, Greek yogurt, lentils and whey protein.")


def coach_reply(query: str, engine: FitnessEngine,
                meal_plan: list = None, workout_plan: list = None) -> str:
    """Intent-based local chatbot that answers questions about the user's plan."""
    q = query.lower().strip()
    a = engine.analysis
    p = engine.profile
    m = a.macros

    def meal_suggestion(slot: str, emoji: str) -> str:
        if not meal_plan:
            return "Generate your plan first and I'll suggest one! 🍽️"
        meal = meal_plan[0]["meals"].get(slot, [None])[0]
        if not meal:
            return "Generate your plan first and I'll suggest one! 🍽️"
        return (f"{emoji} **{meal['name']}** — {meal['kcal']} kcal "
                f"(P {meal['protein']} g / C {meal['carbs']} g / F {meal['fats']} g), "
                f"ready in ~{meal['prep_min']} min.\n\n"
                f"Ingredients: {', '.join(meal['ingredients'])}.")

    if not q:
        return "Tell me what you'd like to know! 😊"

    # --- Calories / energy balance ---
    if any(k in q for k in ["calorie", "tdee", "maintenance", "how much should i eat",
                            "deficit", "surplus", "eat how much"]):
        change = a.target_calories - a.tdee
        direction = ("fat loss" if a.weekly_change_kg < 0
                     else "weight gain" if a.weekly_change_kg > 0 else "maintenance")
        return (f"Your maintenance (TDEE) is **{a.tdee} kcal/day** — your BMR of {a.bmr} kcal "
                f"plus your activity level ({p.activity}).\n\n"
                f"For **{p.goal}** your daily target is **{a.target_calories} kcal** "
                f"({change:+d} kcal vs maintenance), which works out to roughly "
                f"**{abs(a.weekly_change_kg):.2f} kg of {direction} per week**.")
    if "bmr" in q:
        return (f"Your **BMR (Basal Metabolic Rate)** is **{a.bmr} kcal/day** — what your body "
                f"burns at complete rest, calculated with the Mifflin-St Jeor equation. "
                f"Your TDEE of {a.tdee} kcal adds daily activity on top of it.")

    # --- Macros ---
    if "protein" in q:
        return (f"Aim for **{m['protein_g']} g of protein per day** "
                f"(≈{round(m['protein_g'] / max(p.weight_kg, 1), 1)} g per kg). "
                f"Best sources on a {p.diet} diet: {_protein_sources(p.diet)}")
    if any(k in q for k in ["macro", "carbs", "carbohydrate", "fats", "fat intake"]):
        return (f"Your daily macro split at {a.target_calories} kcal:\n\n"
                f"- 🥩 Protein: **{m['protein_g']} g** ({m['protein_kcal']} kcal)\n"
                f"- 🍞 Carbs: **{m['carbs_g']} g** ({m['carbs_kcal']} kcal)\n"
                f"- 🥑 Fats: **{m['fats_g']} g** ({m['fats_kcal']} kcal)")

    # --- Body metrics ---
    if any(k in q for k in ["bmi", "overweight", "underweight", "obese",
                            "healthy weight", "my weight", "body fat"]):
        return (f"Your **BMI is {a.bmi}** — {a.bmi_emoji} *{a.bmi_category}* (WHO scale).\n\n"
                f"For your height ({p.height_cm} cm), a healthy weight is "
                f"**{a.healthy_weight_min}–{a.healthy_weight_max} kg** and you currently "
                f"weigh {p.weight_kg} kg.\n\n"
                f"📌 For Asian populations the WHO recommends lower BMI cut-offs "
                f"(≥23 overweight, ≥25 obese) — your Asian-band category is "
                f"**{a.bmi_category_asian}**.")

    # --- Meals ---
    if "breakfast" in q:
        return meal_suggestion("Breakfast", "🍳 Today's breakfast idea:")
    if "lunch" in q:
        return meal_suggestion("Lunch", "☀️ Today's lunch idea:")
    if "dinner" in q:
        return meal_suggestion("Dinner", "🌙 Today's dinner idea:")
    if "snack" in q:
        return meal_suggestion("Snacks", "🥜 A great snack option:")
    if any(k in q for k in ["grocery", "shopping", "ingredient"]):
        return "Check the 🍽️ **Meal Plan** page — there's a full weekly grocery list at the bottom! 🛒"

    # --- Workout ---
    if any(k in q for k in ["workout", "exercise", "gym", "train", "today"]):
        if workout_plan:
            today = workout_plan[0]
            if not today["exercises"]:
                return f"Today ({today['day']}) is a **rest day** 😴 — {today['note']}"
            ex_list = "\n".join(f"- **{e['name']}** — {e['prescription']} ({e['muscle']})"
                                for e in today["exercises"])
            return (f"Today is **{today['day']}: {today['focus']}** "
                    f"(~{today['duration_min']} min, ~{today['est_kcal']} kcal).\n\n"
                    f"{ex_list}\n\n_{today['note']}_")
        return "Generate your plan first and I'll walk you through today's workout! 💪"
    if "cardio" in q:
        return ("For fat loss, 2–3 HIIT sessions (20–30 min) or 30–45 min of brisk walking / "
                "cycling per week is plenty. For muscle gain, keep cardio light — too much "
                "can interfere with recovery.")
    if "rest day" in q or "recovery" in q:
        return ("Recovery is training too: sleep 7–9 hours, hydrate well and eat enough "
                "protein. Muscles grow while you rest, not while you lift. 🛌")

    # --- Water ---
    if any(k in q for k in ["water", "drink", "thirst", "hydration"]):
        return (f"Target **{a.water_ml / 1000:.1f} L ({a.water_ml} ml)** of water per day — "
                f"about 35 ml per kg of body weight. Drink more on heavy training days! 💧")

    # --- Timeline / weight change ---
    if any(k in q for k in ["lose weight", "gain weight", "how long", "how fast",
                            "timeline", "when will i"]):
        return (f"At your current target of {a.target_calories} kcal/day, expect about "
                f"**{abs(a.weekly_change_kg):.2f} kg per week**. Healthy, sustainable change "
                f"is 0.25–1 kg per week — patience and consistency beat crash diets, always. 🐢💪")

    # --- Motivation ---
    if any(k in q for k in ["motivat", "inspire", "tired", "give up", "lazy",
                            "unmotivated", "discipline"]):
        return ("Discipline beats motivation. Motivation is a feeling — discipline is a habit. "
                "Show up even at 20% effort. Your future self is built one workout at a time. 🔥")

    # --- Plan summary ---
    if any(k in q for k in ["summary", "my plan", "recap", "overview", "tell me about"]):
        training_days = sum(1 for d in (workout_plan or []) if d["exercises"])
        return (f"**Your plan at a glance, {p.name}:**\n\n"
                f"- 🎯 Goal: **{p.goal}** on a **{p.diet}** diet\n"
                f"- 🔥 **{a.target_calories} kcal/day** (TDEE {a.tdee}, BMR {a.bmr})\n"
                f"- 🥩 Macros: P **{m['protein_g']} g** • C **{m['carbs_g']} g** • F **{m['fats_g']} g**\n"
                f"- 🏋️ **{training_days} training days** per week\n"
                f"- 💧 **{a.water_ml / 1000:.1f} L** of water daily")

    # --- Greetings / small talk ---
    if any(k in q for k in ["hello", " hi", "hey", "namaste", "hola", "good morning",
                            "good evening", "good afternoon"]):
        return f"Hey {p.name}! 👋 Great to see you. What would you like to work on today?"
    if "thank" in q:
        return "Anytime! 💪 Now go crush today's plan."
    if "who are you" in q or "what can you" in q:
        return ("I'm your **FitAI coach** 🤖 — I can explain your calories & macros, suggest "
                "meals, walk you through your workouts, remind you about water, and keep you "
                "motivated. 100% local, 100% yours!")

    return ("Good question! I can help with your **calorie target**, **macros**, **BMI**, "
            "today's **meals** or **workout**, **water intake**, your **grocery list**, or just "
            "a dose of **motivation**. What would you like to know? 😊")
