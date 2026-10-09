# 💪 FitAI — AI Fitness & Diet Companion

A professional, **fully-local** Streamlit web app that turns your basic body
metrics into a complete, personalised health plan — diet, workouts, progress
tracking and an AI coach chat. No sign-up, no cloud, no API keys. **Your data
never leaves your machine.** 🔒

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-1.38%2B-FF4B4B)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Features

| Page | What it does |
| --- | --- |
| 🏠 **Dashboard** | BMI (WHO + Asian cut-offs), BMR, TDEE, daily calorie target, macro split donut, hydration target, healthy weight range, personalised coaching tips |
| 🍽️ **Meal Plan** | 7-day personalised meal plan (Indian + international cuisine) matched to your calorie target, diet preference & macros — plus an auto-generated **weekly grocery list** |
| 🏋️ **Workout Plan** | 7-day goal-specific training blueprint (fat-loss / muscle-building / maintenance splits) with sets, reps, equipment and a coach's tip per exercise |
| 📈 **Progress** | Local weight tracker with trend chart, stats and CSV export |
| 🤖 **AI Coach** | Local chat assistant that answers questions about *your* plan — calories, macros, meals, workouts, water, motivation |

**Extras:** save/load profile • one-click Markdown report export • professional
UI (custom CSS theme, KPI cards, BMI gauge, donut chart).

---

## 🚀 Quick Start

```bash
# 1. Clone / copy this folder, then:
cd fitness_ai_companion

# 2. (Recommended) create a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

# 3. Install the single dependency
pip install -r requirements.txt

# 4. Run the app
streamlit run main.py
```

The app opens at **http://localhost:8501** — fill in your profile in the
sidebar and click **🚀 Generate My AI Plan**.

---

## 🧠 How the "AI" works

There is no fake progress bar and no hard-coded meal — the engine genuinely
computes your plan:

1. **Analysis** — standard scientific formulas:
   * **BMI** — WHO classification (plus Asian population cut-offs)
   * **BMR** — Mifflin-St Jeor equation (1990)
   * **TDEE** — BMR × Harris-Benedict activity multiplier
   * **Calorie target** — TDEE ± goal adjustment, floored at safe minimums
     (1200 kcal women / 1500 kcal men)
   * **Macros** — protein 1.8–2.0 g/kg body weight, fats ≈ 28% of energy,
     carbs = remainder
   * **Water** — ≈ 35 ml per kg body weight
2. **Meal plan** — filters a curated database of 30+ meals (with full macros
   and ingredients) by your diet preference, then picks meals per slot
   (breakfast 25% / lunch 35% / dinner 30% / snacks 10%) closest to each
   slot's calorie target, varying meals across the week.
3. **Workout plan** — a 7-day split chosen by your goal (HIIT + strength for
   fat loss, Push/Pull/Legs for muscle gain, full-body + cardio to maintain).
4. **AI Coach** — intent-based local chatbot that answers using *your*
   computed numbers and generated plans.

Everything is deterministic, transparent and runs offline.

---

## 📁 Project Structure

```
fitness_ai_companion/
├── main.py                  # Streamlit UI: 5 pages, components, exports
├── config.py                # App settings & constants
├── requirements.txt         # Single dependency: streamlit
├── assets/
│   └── styles.css           # Professional custom theme
├── utils/
│   ├── calculations.py      # BMI / BMR / TDEE / macros / water (scientific)
│   └── database.py          # 30+ meals & 28 exercises with full macros
├── engine/
│   └── recommender.py       # Recommendation engine + AI Coach chat logic
└── data/                    # profile.json & progress.json (created at runtime)
```

The code is split into **UI / domain logic / data** layers, fully type-hinted
and documented — the way a production project should be structured.

---

## 🍲 Diet preferences supported

**Vegetarian** • **Non-Vegetarian** • **Vegan** • **Keto** — the meal database
is tagged per meal, so the plan only ever suggests food you actually eat.
The cuisine mix is Indian-first (poha, upma, idli, rajma, dal, paneer, sattu…)
plus international options (quinoa bowls, grilled chicken, tofu stir-fry…).

---

## 📸 Screenshots

> Run the app locally to see the dashboard, meal plan, workout blueprint,
> progress tracker and AI coach in action.

---

## ⚠️ Disclaimer

FitAI provides general informational guidance only and is **not** a substitute
for professional medical, nutritional or fitness advice. Consult a qualified
healthcare provider before starting any diet or exercise programme.

---

## 📄 License

MIT License — feel free to use, modify and share.

**Built with ❤️ using Python & Streamlit.**
