import json
import os
import re
from urllib.parse import urlencode
from urllib.request import urlopen

from django.utils import timezone

from .ai import generate_json_completion
from .models import BotBehaviorConfig, ChatMessage, CustomerBotBehaviorOverride, HealthGoal, Recommendation


def customer_analytics(user):
    profile = user.health_profile
    today = timezone.localdate()
    today_meals = user.meal_entries.filter(consumed_at__date=today)
    total_calories = sum(meal.calories for meal in today_meals)

    score = min(
        100,
        round(
            min(profile.steps / 100, 30)
            + min(profile.water_oz / 3, 25)
            + min(float(profile.sleep_hours) * 5, 25)
            + min(profile.workouts_per_week * 5, 20)
        ),
    )

    insights = []
    if profile.water_oz < 64:
        insights.append("Hydration is below a strong daily target. Increase water earlier in the day.")
    if float(profile.sleep_hours) < 7:
        insights.append("Sleep is limiting recovery. A more stable wind-down routine would improve readiness.")
    if profile.steps < 8000:
        insights.append("Movement is below the current target. A post-meal walk is the simplest recovery action.")
    if total_calories == 0:
        insights.append("No meals logged today. Logging intake will improve recommendation quality.")
    if not insights:
        insights.append("Your routine looks steady today. Focus on consistency rather than adding complexity.")

    recommendation = Recommendation.objects.filter(category=preferred_recommendation_category(user)).first() or Recommendation.objects.first()

    return {
        "steps": profile.steps,
        "water_oz": profile.water_oz,
        "sleep_hours": profile.sleep_hours,
        "workouts_per_week": profile.workouts_per_week,
        "consistency_score": score,
        "total_calories": total_calories,
        "goal_count": user.health_goals.count(),
        "insights": insights,
        "primary_recommendation": recommendation,
    }


def preferred_recommendation_category(user):
    profile = user.health_profile
    if float(profile.sleep_hours) < 7 or profile.water_oz < 64:
        return Recommendation.Categories.WELLNESS
    if profile.steps < 8000 or profile.workouts_per_week < 3:
        return Recommendation.Categories.EXERCISE
    return Recommendation.Categories.DIET


def relevant_recommendations(user, limit=3):
    preferred = preferred_recommendation_category(user)
    primary = list(Recommendation.objects.filter(category=preferred)[:limit])
    if len(primary) < limit:
        remaining = Recommendation.objects.exclude(id__in=[item.id for item in primary])[: limit - len(primary)]
        primary.extend(list(remaining))
    return primary


def _resolved_behavior_instructions(user, global_instructions=None, customer_override=None):
    if global_instructions is None:
        global_config, _ = BotBehaviorConfig.objects.get_or_create()
        global_instructions = global_config.instructions

    if customer_override is None:
        override = CustomerBotBehaviorOverride.objects.filter(user=user).first()
        customer_override = override.instructions if override else ""

    behavior_parts = [global_instructions.strip()]
    if customer_override and customer_override.strip():
        behavior_parts.append(f"Customer-specific override: {customer_override.strip()}")
    return "\n\n".join([part for part in behavior_parts if part])


def _keyword_food_query(incoming_message):
    lowered = (incoming_message or "").lower()
    candidates = [
        "chicken breast",
        "greek yogurt",
        "salmon",
        "eggs",
        "oats",
        "brown rice",
        "banana",
        "avocado",
    ]
    for candidate in candidates:
        if candidate in lowered:
            return candidate
    return None


def _usda_food_hint(food_query):
    if not food_query:
        return None

    api_key = os.getenv("FOOD_DATA_GOV")
    if not api_key:
        return None

    params = urlencode({"query": food_query, "pageSize": 1, "api_key": api_key})
    url = f"https://api.nal.usda.gov/fdc/v1/foods/search?{params}"

    try:
        with urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    foods = payload.get("foods") or []
    if not foods:
        return None

    top = foods[0]
    nutrients = {item.get("nutrientName"): item.get("value") for item in top.get("foodNutrients", [])}
    calories = nutrients.get("Energy")
    protein = nutrients.get("Protein")
    carbs = nutrients.get("Carbohydrate")
    fat = nutrients.get("Total lipid (fat)")

    parts = []
    if calories is not None:
        parts.append(f"{calories} kcal")
    if protein is not None:
        parts.append(f"{protein}g protein")
    if carbs is not None:
        parts.append(f"{carbs}g carbs")
    if fat is not None:
        parts.append(f"{fat}g fat")
    if not parts:
        return None
    return f"USDA check for {food_query}: " + ", ".join(parts)


def detect_goal_from_message(user, incoming_message):
    text = (incoming_message or "").strip()
    if not text:
        return None

    lowered = text.lower()
    trigger_phrases = ["my goal is", "i want to", "i would like to", "i need to", "goal:", "my target is"]
    if not any(phrase in lowered for phrase in trigger_phrases):
        return None

    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = re.sub(r"^[\-\*\s]+", "", cleaned)
    if len(cleaned) > 180:
        cleaned = cleaned[:180].rsplit(" ", 1)[0]

    existing_titles = set(user.health_goals.values_list("title", flat=True))
    if cleaned in existing_titles:
        return None

    next_sort = user.health_goals.count()
    HealthGoal.objects.create(user=user, title=cleaned, sort_order=next_sort)
    return cleaned


def build_chat_response(user, channel, incoming_message, global_instructions=None, customer_override=None):
    analytics = customer_analytics(user)
    recommendation = analytics["primary_recommendation"]
    prefix = "From a coaching view" if channel == ChatMessage.Channels.COACH else "Based on your saved health data"
    guidance = recommendation.guidance if recommendation else "stay consistent with meals, movement, and recovery."

    behavior_instructions = _resolved_behavior_instructions(
        user,
        global_instructions=global_instructions,
        customer_override=customer_override,
    )

    system_prompt = (
        "You are a health coaching assistant for a wellness app. "
        "Follow the behavior instructions strictly when composing responses. "
        "Return JSON with keys: summary, health_tip, reply. "
        "Keep reply practical, safe, and under 120 words.\n\n"
        f"Behavior instructions:\n{behavior_instructions}"
    )
    user_prompt = (
        f"Channel: {channel}\n"
        f"Customer consistency score: {analytics['consistency_score']}\n"
        f"Hydration: {analytics['water_oz']} oz\n"
        f"Sleep: {analytics['sleep_hours']} hours\n"
        f"Steps: {analytics['steps']}\n"
        f"Recommended next step: {guidance}\n"
        f"Incoming message: {incoming_message}"
    )
    generated = generate_json_completion(system_prompt, user_prompt)
    reply = (generated.get("reply") or "").strip() if isinstance(generated, dict) else ""
    if reply:
        return reply

    focus_actions = []
    if analytics["water_oz"] < 64:
        focus_actions.append("Add 16-24 oz of water before lunch.")
    if float(analytics["sleep_hours"]) < 7:
        focus_actions.append("Set a fixed wind-down time tonight to protect 7+ hours of sleep.")
    if analytics["steps"] < 8000:
        focus_actions.append("Add one 15-minute walk after a meal today.")

    recommendation_lines = []
    for item in relevant_recommendations(user, limit=2):
        recommendation_lines.append(f"{item.title}: {item.guidance}")

    usda_hint = _usda_food_hint(_keyword_food_query(incoming_message))

    if not focus_actions:
        focus_actions.append("Keep your current routine steady and repeat what worked this week.")

    lines = [
        f"{prefix}, your current consistency score is {analytics['consistency_score']}.",
        "Today\'s priority actions:",
        f"1) {focus_actions[0]}",
    ]
    if len(focus_actions) > 1:
        lines.append(f"2) {focus_actions[1]}")

    if recommendation_lines:
        lines.append(f"Recommendation library match: {recommendation_lines[0]}")
    if usda_hint:
        lines.append(usda_hint)

    return " ".join(lines)


def serialize_recommendation(recommendation):
    if not recommendation:
        return None

    return {
        "id": recommendation.id,
        "title": recommendation.title,
        "category": recommendation.category,
        "guidance": recommendation.guidance,
        "analytics_focus": recommendation.analytics_focus,
    }


def customer_summary_payload(user):
    analytics = customer_analytics(user)
    goals = list(user.health_goals.values_list("title", flat=True))

    return {
        "profile": {
            "daily_recommendation": user.health_profile.daily_recommendation,
            "wellness_focus": user.health_profile.wellness_focus,
            "steps": user.health_profile.steps,
            "water_oz": user.health_profile.water_oz,
            "sleep_hours": float(user.health_profile.sleep_hours),
            "workouts_per_week": user.health_profile.workouts_per_week,
        },
        "goals": goals,
        "analytics": {
            "steps": analytics["steps"],
            "water_oz": analytics["water_oz"],
            "sleep_hours": float(analytics["sleep_hours"]),
            "workouts_per_week": analytics["workouts_per_week"],
            "consistency_score": analytics["consistency_score"],
            "total_calories": analytics["total_calories"],
            "goal_count": analytics["goal_count"],
            "insights": analytics["insights"],
        },
        "recommendations": {
            "primary": serialize_recommendation(analytics["primary_recommendation"]),
            "relevant": [serialize_recommendation(item) for item in relevant_recommendations(user)],
        },
    }