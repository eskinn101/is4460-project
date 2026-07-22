from django.utils import timezone

from .models import ChatMessage, Recommendation


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


def build_chat_response(user, channel, incoming_message):
    analytics = customer_analytics(user)
    recommendation = analytics["primary_recommendation"]
    prefix = "From a coaching view" if channel == ChatMessage.Channels.COACH else "Based on your saved health data"
    guidance = recommendation.guidance if recommendation else "stay consistent with meals, movement, and recovery."
    return (
        f"{prefix}, your consistency score is {analytics['consistency_score']}. "
        f"Top next step: {guidance} You mentioned: '{incoming_message[:90]}'."
    )