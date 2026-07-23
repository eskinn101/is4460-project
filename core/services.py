import json

from django.utils import timezone

from .ai import generate_json_completion
from .models import ChatMessage, Recommendation


def customer_analytics(user):
    profile = getattr(user, "health_profile", None)
    today = timezone.localdate()
    today_meals = user.meal_entries.filter(consumed_at__date=today)
    total_calories = sum(meal.calories for meal in today_meals)

    if profile is None:
        recommendation = Recommendation.objects.first()
        return {
            "steps": 0,
            "water_oz": 0,
            "sleep_hours": 0,
            "workouts_per_week": 0,
            "consistency_score": 0,
            "total_calories": total_calories,
            "goal_count": 0,
            "insights": ["No customer health profile is attached to this account yet."],
            "primary_recommendation": recommendation,
        }

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
    profile = getattr(user, "health_profile", None)
    if profile is None:
        return Recommendation.Categories.WELLNESS
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


def _default_partner_matches(partners):
    ranked_partners = sorted(partners, key=lambda partner: partner.get("match_score", 0), reverse=True)[:3]
    return [
        {
            "slug": partner.get("slug"),
            "name": partner.get("name"),
            "reason": partner.get("recommendation_reason", "Matches your current activity and nutrition goals."),
        }
        for partner in ranked_partners
    ]


def build_ai_guidance(user, analytics=None, recommendations=None, meals=None, partners=None, incoming_message=None, purpose="dashboard"):
    analytics = analytics or customer_analytics(user)
    recommendations = recommendations or relevant_recommendations(user)
    meals = meals or list(user.meal_entries.order_by("-consumed_at")[:5])
    partners = partners or []

    primary_recommendation = analytics["primary_recommendation"]
    payload = {
        "purpose": purpose,
        "profile": {
            "consistency_score": analytics["consistency_score"],
            "total_calories": analytics["total_calories"],
            "goal_count": analytics["goal_count"],
            "steps": analytics["steps"],
            "water_oz": analytics["water_oz"],
            "sleep_hours": float(analytics["sleep_hours"]),
            "workouts_per_week": analytics["workouts_per_week"],
        },
        "insights": analytics["insights"],
        "primary_recommendation": {
            "title": primary_recommendation.title if primary_recommendation else None,
            "category": primary_recommendation.category if primary_recommendation else None,
            "guidance": primary_recommendation.guidance if primary_recommendation else None,
            "analytics_focus": primary_recommendation.analytics_focus if primary_recommendation else None,
        },
        "secondary_recommendations": [
            {
                "title": recommendation.title,
                "category": recommendation.category,
                "guidance": recommendation.guidance,
                "analytics_focus": recommendation.analytics_focus,
            }
            for recommendation in recommendations
        ],
        "recent_meals": [
            {
                "meal_name": meal.meal_name,
                "time_of_day": meal.time_of_day,
                "calories": meal.calories,
                "notes": meal.notes,
            }
            for meal in meals
        ],
        "partners": [
            {
                "slug": partner.get("slug"),
                "name": partner.get("name"),
                "category": partner.get("category"),
                "match_score": partner.get("match_score"),
                "recommendation_reason": partner.get("recommendation_reason"),
            }
            for partner in partners
        ],
        "incoming_message": incoming_message,
    }

    system_prompt = (
        "You are a wellness assistant for a prototype health coaching app. "
        "Return concise valid JSON only. Do not include markdown or commentary."
    )
    user_prompt = (
        "Generate personalized guidance from this JSON input. "
        "Return keys: summary, meal_tip, health_tip, partner_tip, chat_reply, partner_matches. "
        "partner_matches must be a list of objects with slug, name, and reason.\n\n"
        f"{json.dumps(payload)}"
    )

    ai_result = generate_json_completion(system_prompt, user_prompt)
    partner_matches = ai_result.get("partner_matches") if isinstance(ai_result, dict) else []
    if not isinstance(partner_matches, list) or not partner_matches:
        partner_matches = _default_partner_matches(partners)

    summary = ai_result.get("summary") if isinstance(ai_result, dict) else ""
    meal_tip = ai_result.get("meal_tip") if isinstance(ai_result, dict) else ""
    health_tip = ai_result.get("health_tip") if isinstance(ai_result, dict) else ""
    partner_tip = ai_result.get("partner_tip") if isinstance(ai_result, dict) else ""
    chat_reply = ai_result.get("chat_reply") if isinstance(ai_result, dict) else ""

    if not summary:
        summary = f"Your consistency score is {analytics['consistency_score']}."
    if not meal_tip:
        meal_tip = primary_recommendation.guidance if primary_recommendation else "Keep meals balanced with protein, fiber, and hydration."
    if not health_tip:
        health_tip = analytics["insights"][0]
    if not partner_tip:
        partner_tip = "Match partners to the highest relevance scores and the habits you want to reinforce."
    if not chat_reply:
        prefix = "From a coaching view" if purpose == "chat" else "Based on your saved health data"
        guidance = primary_recommendation.guidance if primary_recommendation else "stay consistent with meals, movement, and recovery."
        if incoming_message:
            chat_reply = (
                f"{prefix}, your consistency score is {analytics['consistency_score']}. "
                f"Top next step: {guidance} You mentioned: '{incoming_message[:90]}'."
            )
        else:
            chat_reply = f"{prefix}, your next step is {guidance}"

    return {
        "summary": summary,
        "meal_tip": meal_tip,
        "health_tip": health_tip,
        "partner_tip": partner_tip,
        "chat_reply": chat_reply,
        "partner_matches": partner_matches,
    }


def build_chat_response(user, channel, incoming_message):
    analytics = customer_analytics(user)
    ai_guidance = build_ai_guidance(user, analytics=analytics, incoming_message=incoming_message, purpose="chat")
    prefix = "From a coaching view" if channel == ChatMessage.Channels.COACH else "Based on your saved health data"
    if ai_guidance.get("chat_reply"):
        return ai_guidance["chat_reply"]

    recommendation = analytics["primary_recommendation"]
    guidance = recommendation.guidance if recommendation else "stay consistent with meals, movement, and recovery."
    return (
        f"{prefix}, your consistency score is {analytics['consistency_score']}. "
        f"Top next step: {guidance} You mentioned: '{incoming_message[:90]}'."
    )


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
    ai_guidance = build_ai_guidance(user, analytics=analytics, recommendations=relevant_recommendations(user), purpose="summary")
    profile = getattr(user, "health_profile", None)

    return {
        "profile": {
            "daily_recommendation": profile.daily_recommendation if profile else "",
            "wellness_focus": profile.wellness_focus if profile else "",
            "steps": profile.steps if profile else 0,
            "water_oz": profile.water_oz if profile else 0,
            "sleep_hours": float(profile.sleep_hours) if profile else 0,
            "workouts_per_week": profile.workouts_per_week if profile else 0,
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
        "ai_guidance": ai_guidance,
    }