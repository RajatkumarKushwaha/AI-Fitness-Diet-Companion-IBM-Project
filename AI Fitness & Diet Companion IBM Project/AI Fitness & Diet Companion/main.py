"""FitAI — AI Fitness & Diet Companion.

A professional, fully-local Streamlit dashboard that turns basic body
metrics into a complete personalised health plan:

    🏠 Dashboard   — BMI / BMR / TDEE / calorie & macro targets, coaching tips
    🍽️ Meal Plan   — 7-day personalised meals + weekly grocery list
    🏋️ Workout Plan — 7-day goal-specific training blueprint
    📈 Progress    — local weight tracker with trend chart
    🤖 AI Coach    — local chat assistant that knows your plan

Run locally:
    pip install -r requirements.txt
    streamlit run main.py
"""

import json
import math
from datetime import date
from pathlib import Path

import streamlit as st

from config import (
    APP_ICON,
    APP_NAME,
    APP_TAGLINE,
    DATA_DIR,
    DIET_PREFERENCES,
    GENDERS,
    GOALS,
    PAGES,
)
from engine.recommender import FitnessEngine, UserProfile, coach_reply
from utils.calculations import ACTIVITY_LEVELS

# ------------------------------------------------------------ data files ---
DATA_DIR.mkdir(parents=True, exist_ok=True)
PROFILE_FILE = DATA_DIR / "profile.json"
PROGRESS_FILE = DATA_DIR / "progress.json"

# ------------------------------------------------------------ page setup ---
st.set_page_config(
    page_title=f"{APP_NAME} — {APP_TAGLINE}",
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_css() -> None:
    """Inject the custom theme stylesheet."""
    css_path = Path(__file__).resolve().parent / "assets" / "styles.css"
    st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>",
                unsafe_allow_html=True)


load_css()


# ============================================================== components ==
def hero() -> None:
    """Gradient hero banner."""
    st.markdown(
        f"""
        <div class="hero">
            <h1>{APP_ICON} {APP_NAME} — {APP_TAGLINE}</h1>
            <p>Personalised nutrition &amp; training, computed locally from your body
            metrics. No sign-up. No cloud. Your data stays on your machine. 🔒</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, sub: str, color: str = "#ff6b6b") -> None:
    """A single KPI card."""
    st.markdown(
        f"""
        <div class="metric-card" style="border-top-color:{color};">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def bmi_gauge(bmi: float, category: str, emoji: str) -> str:
    """Horizontal WHO BMI scale with a marker at the user's BMI."""
    lo, hi = 15.0, 40.0
    pct = max(0.0, min(100.0, (bmi - lo) / (hi - lo) * 100.0))

    def seg(a: float, b: float, color: str) -> str:
        left = (a - lo) / (hi - lo) * 100.0
        width = (b - a) / (hi - lo) * 100.0
        return (f'<div class="gauge-seg" style="left:{left:.2f}%; '
                f'width:{width:.2f}%; background:{color};"></div>')

    return f"""
    <div class="gauge-wrap">
        <div class="gauge-track">
            {seg(15, 18.5, '#eab308')}
            {seg(18.5, 25, '#22c55e')}
            {seg(25, 30, '#f97316')}
            {seg(30, 40, '#ef4444')}
            <div class="gauge-marker" style="left:{pct:.1f}%;;">▼</div>
        </div>
        <div class="gauge-labels">
            <span>15</span><span>18.5</span><span>25</span><span>30</span><span>40</span>
        </div>
        <div class="gauge-value">{emoji} BMI {bmi} — {category}</div>
    </div>
    """


def macros_donut(macros: dict, target_kcal: int) -> str:
    """SVG donut chart of the daily calorie split (protein / carbs / fats)."""
    r, cx, cy = 70, 100, 100
    circumference = 2 * math.pi * r
    segments = [
        ("Protein", macros["protein_kcal"], "#ff6b6b"),
        ("Carbs", macros["carbs_kcal"], "#4ecdc4"),
        ("Fats", macros["fats_kcal"], "#ffb347"),
    ]
    total = sum(s[1] for s in segments) or 1
    offset = 0.0
    circles = ""
    for _, value, color in segments:
        dash = value / total * circumference
        circles += (
            f'<circle r="{r}" cx="{cx}" cy="{cy}" fill="transparent" stroke="{color}" '
            f'stroke-width="26" stroke-dasharray="{dash:.2f} {circumference - dash:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {cx} {cy})" />'
        )
        offset += dash
    return f"""
    <svg viewBox="0 0 200 200" class="donut">
        {circles}
        <text x="100" y="96" text-anchor="middle" class="donut-num">{target_kcal}</text>
        <text x="100" y="118" text-anchor="middle" class="donut-unit">kcal / day</text>
    </svg>
    """


def render_footer() -> None:
    st.markdown(
        f"""
        <div class="app-footer">
            🔒 {APP_NAME} runs 100% locally — your data never leaves your machine.
            Built with Python &amp; Streamlit. This app is informational and is not a
            substitute for professional medical advice.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ================================================================ sidebar ==
def render_sidebar() -> tuple:
    """Profile form + navigation. Returns (profile_values, generate, page)."""
    with st.sidebar:
        st.markdown(
            f'<div class="side-logo">{APP_ICON} <b>{APP_NAME}</b></div>',
            unsafe_allow_html=True,
        )
        page = st.radio("Navigate", PAGES, label_visibility="collapsed")
        st.markdown("---")
        st.subheader("👤 Your Profile")

        # Apply a profile loaded via the "Load" button (one-shot)
        saved = st.session_state.pop("loaded_profile", None) or {}

        name = st.text_input("Name", value=saved.get("name", "Aarav"))
        age = st.slider("Age (years)", 10, 100, int(saved.get("age", 25)))
        gender = st.radio(
            "Gender", GENDERS,
            index=GENDERS.index(saved["gender"]) if saved.get("gender") in GENDERS else 0,
        )
        c1, c2 = st.columns(2)
        with c1:
            weight = st.number_input("Weight (kg)", 30.0, 250.0,
                                     float(saved.get("weight_kg", 70.0)), step=0.5)
        with c2:
            height = st.number_input("Height (cm)", 100.0, 250.0,
                                     float(saved.get("height_cm", 170.0)), step=0.5)
        activity = st.selectbox(
            "Activity level", list(ACTIVITY_LEVELS.keys()),
            index=list(ACTIVITY_LEVELS).index(saved["activity"])
            if saved.get("activity") in ACTIVITY_LEVELS else 1,
        )
        goal = st.selectbox(
            "🎯 Fitness goal", GOALS,
            index=GOALS.index(saved["goal"]) if saved.get("goal") in GOALS else 0,
        )
        diet = st.selectbox(
            "🥗 Diet preference", DIET_PREFERENCES,
            index=DIET_PREFERENCES.index(saved["diet"])
            if saved.get("diet") in DIET_PREFERENCES else 0,
        )
        st.markdown("---")
        generate = st.button("🚀 Generate My AI Plan", type="primary",
                             width="stretch")
        save = st.button("💾 Save Profile", width="stretch")
        load = st.button("📂 Load Saved Profile", width="stretch")

        if save:
            payload = {
                "name": name, "age": age, "gender": gender,
                "weight_kg": weight, "height_cm": height,
                "activity": activity, "goal": goal, "diet": diet,
            }
            PROFILE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            st.toast("Profile saved ✔", icon="💾")

        if load:
            if PROFILE_FILE.exists():
                st.session_state["loaded_profile"] = json.loads(
                    PROFILE_FILE.read_text(encoding="utf-8"))
                st.rerun()
            else:
                st.toast("No saved profile found yet", icon="⚠️")

    profile_values = {
        "name": name, "age": age, "gender": gender,
        "weight_kg": weight, "height_cm": height,
        "activity": activity, "goal": goal, "diet": diet,
    }
    return profile_values, generate, page


# ================================================================ dashboard ==
def render_dashboard(engine: FitnessEngine) -> None:
    a = engine.analysis
    p = engine.profile
    m = a.macros
    hero()
    st.markdown(
        f"<h2 class='section-title'>Welcome back, {p.name} 👋</h2>",
        unsafe_allow_html=True,
    )

    # Row 1 — core metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Body Mass Index", f"{a.bmi}", f"{a.bmi_emoji} {a.bmi_category}", a.bmi_color)
    with c2:
        metric_card("BMR", f"{a.bmr}", "kcal/day at complete rest", "#4ecdc4")
    with c3:
        metric_card("TDEE", f"{a.tdee}", "kcal/day with your activity", "#8b5cf6")
    with c4:
        metric_card("Daily Target", f"{a.target_calories}",
                    f"kcal/day for {p.goal.lower()}", "#ff6b6b")

    # Row 2 — nutrition & hydration targets
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Protein", f"{m['protein_g']} g",
                    f"{round(m['protein_g'] / max(p.weight_kg, 1), 1)} g per kg body weight",
                    "#ff6b6b")
    with c2:
        metric_card("Carbs", f"{m['carbs_g']} g", f"{m['carbs_kcal']} kcal", "#4ecdc4")
    with c3:
        metric_card("Fats", f"{m['fats_g']} g", f"{m['fats_kcal']} kcal", "#ffb347")
    with c4:
        metric_card("Water", f"{a.water_ml / 1000:.1f} L", "daily hydration target", "#38bdf8")

    st.markdown("---")

    # BMI gauge + macros donut
    g1, g2 = st.columns([1.2, 1])
    with g1:
        st.markdown(
            '<div class="card"><h3 style="margin-top:0;">📊 BMI Scale (WHO)</h3>'
            + bmi_gauge(a.bmi, a.bmi_category, a.bmi_emoji)
            + f'<p style="color:#64748b; font-size:0.85rem; margin-bottom:0;">'
              f'Healthy weight for your height ({p.height_cm} cm): '
              f'<b>{a.healthy_weight_min}–{a.healthy_weight_max} kg</b></p>'
              f'<p style="color:#64748b; font-size:0.85rem; margin-bottom:0;">'
              f'For Asian populations, WHO recommends lower cut-offs (≥23 overweight, '
              f'≥25 obese) — your Asian-band category: <b>{a.bmi_category_asian}</b></p>'
            "</div>",
            unsafe_allow_html=True,
        )
    with g2:
        legend = "".join(
            f'<span class="chip" style="background:{color}22; color:{color};">'
            f"● {name} {grams} g</span>"
            for name, grams, color in [
                ("Protein", m["protein_g"], "#ff6b6b"),
                ("Carbs", m["carbs_g"], "#4ecdc4"),
                ("Fats", m["fats_g"], "#ffb347"),
            ]
        )
        weekly = a.weekly_change_kg
        pace = (f"≈ {abs(weekly):.2f} kg fat loss / week" if weekly < 0
                else f"≈ {abs(weekly):.2f} kg gain / week" if weekly > 0
                else "weight maintenance")
        st.markdown(
            '<div class="card"><h3 style="margin-top:0;">🍩 Daily Calorie Split</h3>'
            + macros_donut(m, a.target_calories)
            + f'<div class="donut-legend">{legend}</div>'
            + f'<p style="text-align:center; color:#64748b; font-size:0.85rem; margin-bottom:0;">'
              f'Expected pace: <b>{pace}</b></p>'
            "</div>",
            unsafe_allow_html=True,
        )

    # Coaching tips
    st.markdown("### 💡 Your Personalised Coaching Tips")
    tips = engine.coaching_tips()
    cols = st.columns(2)
    for i, tip in enumerate(tips):
        with cols[i % 2]:
            st.markdown(
                f'<div class="tip-card">🧠 {tip}</div>', unsafe_allow_html=True)

    # Export full report
    st.markdown("---")
    report = build_report_md(
        engine, st.session_state["meal_plan"], st.session_state["workout_plan"])
    st.download_button(
        "⬇️ Download Full Report (Markdown)",
        data=report,
        file_name=f"fitai_plan_{p.name.lower().replace(' ', '_')}.md",
        mime="text/markdown",
    )


# ================================================================ meal plan ==
def render_meal_card(meal: dict) -> None:
    st.markdown(
        f"""
        <div class="meal-card">
            <div class="meal-title">{meal['name']}</div>
            <div>
                <span class="chip">🔥 {meal['kcal']} kcal</span>
                <span class="chip">💪 P {meal['protein']} g</span>
                <span class="chip">🍞 C {meal['carbs']} g</span>
                <span class="chip">🥑 F {meal['fats']} g</span>
                <span class="chip">🍽 Portion {meal.get('portion', '1×')}</span>
                <span class="chip">⏱ {meal['prep_min']} min</span>
            </div>
            <div class="meal-ing"><b>Ingredients:</b> {', '.join(meal['ingredients'])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_meal_plan(engine: FitnessEngine) -> None:
    meal_plan = st.session_state["meal_plan"]
    a = engine.analysis
    hero()
    st.markdown(
        "<h2 class='section-title'>🍽️ Your 7-Day Meal Plan</h2>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Built for **{engine.profile.goal}** on a **{engine.profile.diet}** diet — "
        f"target ≈ **{a.target_calories} kcal/day**, **{a.macros['protein_g']} g protein**. "
        f"💧 Don't forget {a.water_ml / 1000:.1f} L of water!"
    )

    tabs = st.tabs([f"📅 {day['day']}" for day in meal_plan])
    for tab, day in zip(tabs, meal_plan):
        with tab:
            meals = day["meals"]
            cols = st.columns(3)
            for col, (key, label) in zip(cols, [("Breakfast", "🌅 Breakfast"),
                                               ("Lunch", "☀️ Lunch"),
                                               ("Dinner", "🌙 Dinner")]):
                with col:
                    st.markdown(f"#### {label}")
                    for meal in meals[key]:
                        render_meal_card(meal)
            if meals.get("Snacks"):
                st.markdown("#### 🥜 Snacks")
                snack_cols = st.columns(len(meals["Snacks"]))
                for col, meal in zip(snack_cols, meals["Snacks"]):
                    with col:
                        render_meal_card(meal)
            if meals.get("Top-up"):
                st.markdown("#### 💪 Protein Top-up (recommended)")
                render_meal_card(meals["Top-up"][0])
            t = day["totals"]
            st.markdown(
                f"""
                <div class="totals-bar">
                    <b>Daily totals:</b> {t['kcal']} kcal &nbsp;•&nbsp;
                    Protein {t['protein']} g &nbsp;•&nbsp;
                    Carbs {t['carbs']} g &nbsp;•&nbsp;
                    Fats {t['fats']} g
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # Weekly grocery list
    st.markdown("### 🛒 Weekly Grocery List")
    grocery = sorted(engine.grocery_list(meal_plan).items())
    half = (len(grocery) + 1) // 2
    g1, g2 = st.columns(2)
    with g1:
        for item, count in grocery[:half]:
            st.markdown(f'<div class="grocery-item">☐ {item}'
                        f'{f" ×{count}" if count > 1 else ""}</div>',
                        unsafe_allow_html=True)
    with g2:
        for item, count in grocery[half:]:
            st.markdown(f'<div class="grocery-item">☐ {item}'
                        f'{f" ×{count}" if count > 1 else ""}</div>',
                        unsafe_allow_html=True)

    st.markdown("---")
    st.download_button(
        "⬇️ Download Meal Plan + Grocery List (Markdown)",
        data=build_meal_plan_md(engine, meal_plan),
        file_name=f"fitai_meal_plan_{engine.profile.name.lower().replace(' ', '_')}.md",
        mime="text/markdown",
    )


# ============================================================== workout plan ==
def render_workout_plan(engine: FitnessEngine) -> None:
    plan = st.session_state["workout_plan"]
    hero()
    st.markdown(
        "<h2 class='section-title'>🏋️ Your 7-Day Workout Blueprint</h2>",
        unsafe_allow_html=True,
    )
    st.warning("⚠️ Always warm up for 5–10 minutes before training. Stop if you feel "
               "sharp pain — effort is good, pain is not.")

    for day in plan:
        if day["duration_min"]:
            title = (f"{day['day']} — {day['focus']}   •   ~{day['duration_min']} min   •   "
                     f"~{day['est_kcal']} kcal")
        else:
            title = f"{day['day']} — Rest 😴"
        with st.expander(title, expanded=(day["day"] == "Monday")):
            st.markdown(f"_{day['note']}_")
            if not day["exercises"]:
                st.success("Rest day — walk lightly, stretch, sleep 7–9 hours. "
                           "Muscles grow while you recover.")
                continue
            rows = [
                {
                    "Exercise": e["name"],
                    "Muscle Group": e["muscle"],
                    "Equipment": e["equipment"],
                    "Prescription": e["prescription"],
                    "Est. kcal": e["kcal"],
                    "Coach's Tip": e["tip"],
                }
                for e in day["exercises"]
            ]
            st.dataframe(rows, width="stretch", hide_index=True)


# ================================================================= progress ==
def _load_progress() -> list:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def render_progress(engine: FitnessEngine) -> None:
    hero()
    st.markdown(
        "<h2 class='section-title'>📈 Progress Tracker</h2>",
        unsafe_allow_html=True,
    )
    st.caption("🔒 Entries are saved locally in `data/progress.json` — they never leave "
               "your machine.")

    entries = _load_progress()

    c1, c2 = st.columns([1, 1.4])
    with c1:
        st.markdown("#### ➕ Log Today's Weight")
        with st.form("log_form"):
            log_date = st.date_input("Date", value=date.today())
            log_weight = st.number_input(
                "Weight (kg)", 30.0, 250.0,
                float(engine.profile.weight_kg), step=0.1)
            log_note = st.text_input("Note (optional)",
                                     placeholder="e.g. morning, after workout")
            submitted = st.form_submit_button("💾 Save Entry", type="primary")
            if submitted:
                entries.append({"date": log_date.isoformat(),
                                "weight": log_weight, "note": log_note})
                entries.sort(key=lambda e: e["date"])
                PROGRESS_FILE.write_text(json.dumps(entries, indent=2),
                                         encoding="utf-8")
                st.toast("Entry saved ✔", icon="📈")
                st.rerun()

    with c2:
        if entries:
            st.markdown("#### ⚖️ Weight Trend")
            st.line_chart({e["date"]: e["weight"] for e in entries}, height=280)
            first_w, last_w = entries[0]["weight"], entries[-1]["weight"]
            change = round(last_w - first_w, 1)
            m1, m2, m3 = st.columns(3)
            with m1:
                metric_card("First Log", f"{first_w} kg", entries[0]["date"], "#8b5cf6")
            with m2:
                metric_card("Latest", f"{last_w} kg", entries[-1]["date"], "#4ecdc4")
            with m3:
                metric_card("Change", f"{change:+.1f} kg",
                            f"{len(entries)} entries logged",
                            "#22c55e" if change <= 0 else "#ff6b6b")
        else:
            st.info("No entries yet — log your first weight to start the trend. 📉")

    st.markdown("---")
    st.markdown("#### 📜 History")
    if entries:
        st.dataframe(
            [{"Date": e["date"], "Weight (kg)": e["weight"], "Note": e["note"]}
             for e in reversed(entries)],
            width="stretch",
            hide_index=True,
        )
        csv_data = "date,weight_kg,note\n" + "".join(
            f'{e["date"]},{e["weight"]},"{e["note"]}"\n' for e in entries)
        st.download_button("⬇️ Download History (CSV)", data=csv_data,
                           file_name="fitai_progress.csv", mime="text/csv")
        if st.button("🗑️ Clear All Entries"):
            PROGRESS_FILE.write_text("[]", encoding="utf-8")
            st.rerun()
    else:
        st.caption("Your logged entries will appear here.")


# ================================================================ AI coach ==
def render_coach(engine: FitnessEngine) -> None:
    hero()
    st.markdown(
        "<h2 class='section-title'>🤖 AI Coach</h2>", unsafe_allow_html=True)
    st.caption("Ask anything about your plan — calories, meals, workouts, water, "
               "motivation. Runs 100% locally, no API key needed.")

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [{
            "role": "assistant",
            "content": (f"Hey {engine.profile.name}! 👋 I'm your FitAI coach. Try asking: "
                        f"*\"What should I eat for breakfast?\"*, *\"How many calories "
                        f"should I eat?\"* or *\"What is my workout today?\"*"),
        }]

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prompt = st.chat_input("Ask your coach…")
    if prompt:
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        reply = coach_reply(prompt, engine,
                            st.session_state.get("meal_plan"),
                            st.session_state.get("workout_plan"))
        st.session_state.chat_messages.append({"role": "assistant", "content": reply})
        st.rerun()


# ================================================================== exports ==
def build_report_md(engine: FitnessEngine, meal_plan: list, workout_plan: list) -> str:
    """Full personalised report as a Markdown document."""
    a, p, m = engine.analysis, engine.profile, engine.analysis.macros
    lines = [
        f"# {APP_ICON} {APP_NAME} — Personalised Health Report",
        "",
        f"**Prepared for:** {p.name}  ",
        f"**Date:** {date.today().isoformat()}",
        "",
        "## 1. Body Metrics",
        f"- Age: {p.age} years | Gender: {p.gender}",
        f"- Height: {p.height_cm} cm | Weight: {p.weight_kg} kg",
        f"- BMI: **{a.bmi}** ({a.bmi_category}) — Asian-band: {a.bmi_category_asian}",
        f"- BMR (Mifflin-St Jeor): **{a.bmr} kcal/day**",
        f"- TDEE ({p.activity}): **{a.tdee} kcal/day**",
        f"- Daily target for *{p.goal}*: **{a.target_calories} kcal/day**",
        f"- Macros: Protein {m['protein_g']} g • Carbs {m['carbs_g']} g • Fats {m['fats_g']} g",
        f"- Water target: {a.water_ml / 1000:.1f} L/day",
        f"- Healthy weight range for your height: "
        f"{a.healthy_weight_min}–{a.healthy_weight_max} kg",
        f"- Expected pace: ≈ {abs(a.weekly_change_kg):.2f} kg/week",
        "",
        "## 2. 7-Day Meal Plan",
    ]
    for day in meal_plan:
        lines.append(f"### {day['day']}")
        for slot, meals in day["meals"].items():
            for meal in meals:
                lines.append(
                    f"- **{slot}:** {meal['name']} — {meal['kcal']} kcal "
                    f"(P {meal['protein']} g / C {meal['carbs']} g / F {meal['fats']} g)")
        t = day["totals"]
        lines.append(f"  *Totals: {t['kcal']} kcal • P {t['protein']} g • "
                     f"C {t['carbs']} g • F {t['fats']} g*")
        lines.append("")
    lines.append("## 3. 7-Day Workout Plan")
    for day in workout_plan:
        lines.append(f"### {day['day']} — {day['focus']} "
                     f"(~{day['duration_min']} min, ~{day['est_kcal']} kcal)")
        if day["exercises"]:
            for e in day["exercises"]:
                lines.append(f"- {e['name']} — {e['prescription']} "
                             f"({e['muscle']}, {e['equipment']})")
        else:
            lines.append("- Rest day")
        lines.append(f"  *{day['note']}*")
        lines.append("")
    lines.append("## 4. Coaching Tips")
    for tip in engine.coaching_tips():
        lines.append(f"- {tip}")
    lines += [
        "",
        "---",
        "*Generated by FitAI. Informational only — not a substitute for "
        "professional medical advice.*",
    ]
    return "\n".join(lines)


def build_meal_plan_md(engine: FitnessEngine, meal_plan: list) -> str:
    """Meal plan + grocery list as a Markdown document."""
    a = engine.analysis
    lines = [
        f"# 🍽️ {APP_NAME} — 7-Day Meal Plan for {engine.profile.name}",
        "",
        f"Goal: **{engine.profile.goal}** • Diet: **{engine.profile.diet}** • "
        f"Target: **{a.target_calories} kcal/day** • "
        f"Protein: **{a.macros['protein_g']} g/day**",
        "",
    ]
    for day in meal_plan:
        lines.append(f"## {day['day']}")
        for slot, meals in day["meals"].items():
            for meal in meals:
                lines.append(f"- **{slot}:** {meal['name']} — {meal['kcal']} kcal "
                             f"(P {meal['protein']} g / C {meal['carbs']} g / "
                             f"F {meal['fats']} g, ~{meal['prep_min']} min)")
                lines.append(f"  - Ingredients: {', '.join(meal['ingredients'])}")
        t = day["totals"]
        lines.append(f"  **Totals:** {t['kcal']} kcal • P {t['protein']} g • "
                     f"C {t['carbs']} g • F {t['fats']} g")
        lines.append("")
    lines.append("## 🛒 Weekly Grocery List")
    for item, count in sorted(engine.grocery_list(meal_plan).items()):
        lines.append(f"- [ ] {item}" + (f" ×{count}" if count > 1 else ""))
    return "\n".join(lines)


# ====================================================================== main ==
def main() -> None:
    profile_values, generate_clicked, page = render_sidebar()

    if generate_clicked:
        profile = UserProfile(**profile_values)
        with st.spinner("🤖 Analysing your biometrics and building your plan…"):
            engine = FitnessEngine(profile)
            st.session_state["engine"] = engine
            st.session_state["meal_plan"] = engine.build_meal_plan(days=7)
            st.session_state["workout_plan"] = engine.build_workout_plan()
        st.toast("✨ Your personalised plan is ready!", icon="🎉")
        st.balloons()

    engine = st.session_state.get("engine")
    if engine is None:
        hero()
        st.info("👈 Fill in your profile in the sidebar and click "
                "**🚀 Generate My AI Plan** to get started.")
        render_footer()
        return

    if page == "🏠 Dashboard":
        render_dashboard(engine)
    elif page == "🍽️ Meal Plan":
        render_meal_plan(engine)
    elif page == "🏋️ Workout Plan":
        render_workout_plan(engine)
    elif page == "📈 Progress":
        render_progress(engine)
    elif page == "🤖 AI Coach":
        render_coach(engine)

    render_footer()


if __name__ == "__main__":
    main()
