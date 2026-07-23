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
    return f"For {food_query}, USDA lists roughly " + ", ".join(parts)


def _clean_goal_text(text):
    cleaned = re.sub(r"\s+", " ", (text or "")).strip(" .:-")
    cleaned = re.sub(r"^(my goal is|i want to|i would like to|i need to|goal:|my target is)\s+", "", cleaned, flags=re.IGNORECASE)
    if len(cleaned) > 180:
        cleaned = cleaned[:180].rsplit(" ", 1)[0]
    return cleaned


def _normalize_goal_verb(text):
    replacements = {
        "losing": "lose",
        "gaining": "gain",
        "building": "build",
        "improving": "improve",
        "reducing": "reduce",
        "increasing": "increase",
        "decreasing": "decrease",
        "sleeping": "sleep",
        "drinking": "drink",
        "walking": "walk",
        "strength training": "strength train",
    }
    normalized = text.lower()
    for source, target in replacements.items():
        normalized = re.sub(rf"\b{re.escape(source)}\b", target, normalized)
    return normalized


def _condense_goal_segment(segment):
    cleaned = _normalize_goal_verb(segment)
    cleaned = re.sub(r"\b(to|more|better|healthier|weight|body weight)\b", "", cleaned)
    cleaned = re.sub(r"\b(this|next|within|over|for|by)\b.*$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")

    patterns = [
        r"\b(lose|gain|build|improve|reduce|increase|decrease|maintain|walk|run|sleep|hydrate|drink|eat|strength train)\b(?:\s+[a-z0-9]+){0,4}",
        r"\b(high protein|meal prep|stress management|sleep consistency|hydration)\b(?:\s+[a-z0-9]+){0,3}",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            phrase = match.group(0).strip(" ,.-")
            phrase = re.sub(r"\b(fat weight|muscle weight)\b", lambda m: m.group(0).replace(" weight", ""), phrase)
            phrase = re.sub(r"\s+", " ", phrase).strip(" ,.-")
            return phrase

    words = [word for word in re.findall(r"[a-z0-9]+", cleaned) if len(word) > 1]
    return " ".join(words[:5])


def _summarize_goal_text(text):
    cleaned = _clean_goal_text(text)
    if not cleaned:
        return ""

    segments = re.split(r"\b(?:and|while|plus)\b|,|;", cleaned, flags=re.IGNORECASE)
    condensed_segments = []
    for segment in segments:
        phrase = _condense_goal_segment(segment)
        if phrase and phrase not in condensed_segments:
            condensed_segments.append(phrase)

    if not condensed_segments:
        condensed_segments.append(_condense_goal_segment(cleaned))

    summary = ", ".join([segment for segment in condensed_segments if segment])
    summary = re.sub(r"\s+", " ", summary).strip(" ,.-")
    if not summary:
        summary = cleaned
    if len(summary) > 80:
        summary = summary[:80].rsplit(",", 1)[0] or summary[:80].rsplit(" ", 1)[0]
    return summary[:1].upper() + summary[1:]


def _find_goal_match(user, fragment):
    goals = list(user.health_goals.all())
    if not goals:
        return None
    if not fragment:
        return goals[-1]

    lowered_fragment = fragment.lower().strip()
    for goal in goals:
        title = goal.title.lower()
        if lowered_fragment in title or title in lowered_fragment:
            return goal

    fragment_words = {word for word in re.findall(r"[a-z0-9]+", lowered_fragment) if len(word) > 2}
    best_goal = None
    best_score = 0
    for goal in goals:
        goal_words = {word for word in re.findall(r"[a-z0-9]+", goal.title.lower()) if len(word) > 2}
        score = len(fragment_words & goal_words)
        if score > best_score:
            best_score = score
            best_goal = goal
    return best_goal if best_score > 0 else None


def interpret_goal_message(user, incoming_message, commit=True):
    text = (incoming_message or "").strip()
    if not text:
        return None

    lowered = text.lower()

    update_match = re.search(
        r"(?:change|update|edit)\s+(?:my\s+)?goal(?:\s+from\s+(?P<old>.+?))?\s+to\s+(?P<new>.+)",
        text,
        flags=re.IGNORECASE,
    )
    if update_match:
        old_fragment = _clean_goal_text(update_match.group("old") or "")
        new_title = _summarize_goal_text(update_match.group("new"))
        target_goal = _find_goal_match(user, old_fragment)
        if target_goal and new_title:
            previous_title = target_goal.title
            if commit:
                target_goal.title = new_title
                target_goal.save(update_fields=["title"])
            return {
                "action": "updated",
                "old_title": previous_title,
                "title": new_title,
                "message": f"I updated your goal from '{previous_title}' to '{new_title}'.",
            }

    delete_match = re.search(
        r"(?:remove|delete|drop|stop tracking)\s+(?:my\s+)?goal(?:\s+for|\s+to|\s+about)?\s*(?P<target>.+)?",
        text,
        flags=re.IGNORECASE,
    )
    if delete_match and any(keyword in lowered for keyword in ["remove goal", "delete goal", "drop goal", "stop tracking"]):
        target_fragment = _clean_goal_text(delete_match.group("target") or "")
        target_goal = _find_goal_match(user, target_fragment)
        if target_goal:
            removed_title = target_goal.title
            if commit:
                target_goal.delete()
            return {
                "action": "deleted",
                "title": removed_title,
                "message": f"I removed your goal '{removed_title}'.",
            }

    trigger_phrases = ["my goal is", "i want to", "i would like to", "i need to", "goal:", "my target is"]
    if any(phrase in lowered for phrase in trigger_phrases):
        cleaned = _summarize_goal_text(text)
        existing_titles = set(user.health_goals.values_list("title", flat=True))
        if cleaned and cleaned not in existing_titles:
            if commit:
                next_sort = user.health_goals.count()
                HealthGoal.objects.create(user=user, title=cleaned, sort_order=next_sort)
            return {
                "action": "created",
                "title": cleaned,
                "message": f"I saved a new goal for you: '{cleaned}'.",
            }

    return None


def _heuristic_goal_progress(goal_title, analytics):
    title = (goal_title or "").lower()
    score = analytics.get("consistency_score", 0)

    def clamp(value):
        return max(5, min(100, int(round(value))))

    if any(token in title for token in ["lose fat", "fat loss", "weight", "muscle", "protein"]):
        protein_proxy = 65 if analytics.get("total_calories", 0) > 0 else 35
        progress = 0.45 * score + 0.55 * protein_proxy
        status = "on-track" if progress >= 65 else "building"
    elif any(token in title for token in ["sleep", "recovery", "rest"]):
        sleep_hours = float(analytics.get("sleep_hours", 0) or 0)
        sleep_proxy = min(100, (sleep_hours / 8.0) * 100)
        progress = 0.6 * sleep_proxy + 0.4 * score
        status = "on-track" if progress >= 70 else "needs-focus"
    elif any(token in title for token in ["hydrate", "water"]):
        water_oz = analytics.get("water_oz", 0)
        water_proxy = min(100, (water_oz / 80.0) * 100)
        progress = 0.7 * water_proxy + 0.3 * score
        status = "on-track" if progress >= 70 else "needs-focus"
    elif any(token in title for token in ["walk", "run", "steps", "activity", "workout"]):
        steps = analytics.get("steps", 0)
        workouts = analytics.get("workouts_per_week", 0)
        movement_proxy = min(100, (steps / 10000.0) * 80 + min(workouts, 5) * 4)
        progress = 0.65 * movement_proxy + 0.35 * score
        status = "on-track" if progress >= 70 else "building"
    else:
        progress = score
        status = "on-track" if progress >= 70 else "building"

    return {
        "progress_percent": clamp(progress),
        "status": status,
        "note": "Progress estimated from your current analytics profile.",
    }


def _gemini_goal_progress_notes(goals, analytics):
    if not goals:
        return {}

    system_prompt = (
        "You are a health-coaching analytics assistant. "
        "Given active goals and user analytics, estimate progress and give a short next-step note for each goal. "
        "Return strict JSON in this shape: "
        "{\"goals\":[{\"title\":string,\"progress_percent\":int,\"status\":string,\"note\":string}]}."
    )
    user_prompt = (
        f"Analytics: score={analytics.get('consistency_score')}, steps={analytics.get('steps')}, "
        f"water_oz={analytics.get('water_oz')}, sleep_hours={analytics.get('sleep_hours')}, "
        f"workouts_per_week={analytics.get('workouts_per_week')}, calories_today={analytics.get('total_calories')}\n"
        f"Goals: {', '.join(goals)}"
    )
    parsed = generate_json_completion(system_prompt, user_prompt)
    output = {}
    if not isinstance(parsed, dict):
        return output
    goal_items = parsed.get("goals")
    if not isinstance(goal_items, list):
        return output
    for item in goal_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        try:
            progress = int(item.get("progress_percent"))
        except Exception:
            progress = None
        output[title.lower()] = {
            "progress_percent": max(0, min(100, progress)) if progress is not None else None,
            "status": str(item.get("status") or "").strip().lower() or None,
            "note": str(item.get("note") or "").strip() or None,
        }
    return output


def goal_progress_snapshot(user):
    analytics = customer_analytics(user)
    goal_titles = list(user.health_goals.values_list("title", flat=True))
    gemini_notes = _gemini_goal_progress_notes(goal_titles, analytics)

    goal_rows = []
    for goal in user.health_goals.order_by("sort_order", "id"):
        heuristic = _heuristic_goal_progress(goal.title, analytics)
        ai_match = gemini_notes.get(goal.title.lower(), {})

        progress_percent = ai_match.get("progress_percent") if ai_match.get("progress_percent") is not None else heuristic["progress_percent"]
        status = ai_match.get("status") or heuristic["status"]
        note = ai_match.get("note") or heuristic["note"]
        goal_rows.append(
            {
                "id": goal.id,
                "title": goal.title,
                "progress_percent": progress_percent,
                "status": status,
                "note": note,
            }
        )

    return {
        "analytics": analytics,
        "goals": goal_rows,
        "uses_ai": bool(gemini_notes),
    }


def build_chat_payload(user, channel, incoming_message, global_instructions=None, customer_override=None):
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
    sources = {
        "analytics": [
            f"Consistency score: {analytics['consistency_score']}",
            f"Hydration: {analytics['water_oz']} oz",
            f"Sleep: {analytics['sleep_hours']} hours",
            f"Steps: {analytics['steps']}",
        ],
        "recommendations": [],
        "nutrition": [],
        "behavior": [behavior_instructions],
    }
    generated = generate_json_completion(system_prompt, user_prompt)
    reply = (generated.get("reply") or "").strip() if isinstance(generated, dict) else ""
    if reply:
        if isinstance(generated, dict):
            summary = generated.get("summary")
            health_tip = generated.get("health_tip")
            if summary:
                sources["analytics"].append(f"Model summary: {summary}")
            if health_tip:
                sources["recommendations"].append(f"Model health tip: {health_tip}")
        return {"reply": reply, "sources": sources}

    focus_actions = []
    if analytics["water_oz"] < 64:
        focus_actions.append("Add 16-24 oz of water before lunch.")
    if float(analytics["sleep_hours"]) < 7:
        focus_actions.append("Set a fixed wind-down time tonight to protect 7+ hours of sleep.")
    if analytics["steps"] < 8000:
        focus_actions.append("Add one 15-minute walk after a meal today.")

    recommendation_lines = []
    for item in relevant_recommendations(user, limit=2):
        recommendation_lines.append({"title": item.title, "guidance": item.guidance})
        sources["recommendations"].append(f"{item.title}: {item.guidance}")

    usda_hint = _usda_food_hint(_keyword_food_query(incoming_message))
    if usda_hint:
        sources["nutrition"].append(usda_hint)

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
        primary_match = recommendation_lines[0]
        lines.append(
            f"A strong fit from your current plan is {primary_match['title'].lower()}, which recommends that you {primary_match['guidance'][0].lower() + primary_match['guidance'][1:] if len(primary_match['guidance']) > 1 else primary_match['guidance'].lower()}"
        )
    if usda_hint:
        lines.append(usda_hint)

    return {"reply": " ".join(lines), "sources": sources}


def build_chat_response(user, channel, incoming_message, global_instructions=None, customer_override=None):
    return build_chat_payload(
        user,
        channel,
        incoming_message,
        global_instructions=global_instructions,
        customer_override=customer_override,
    )["reply"]


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