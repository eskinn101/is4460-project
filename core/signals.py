from django.contrib.auth import get_user_model
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from .models import ChatMessage, HealthGoal, HealthProfile, MealEntry, Recommendation


@receiver(post_migrate)
def seed_moderation_data(sender, **kwargs):
    if sender.name != "core":
        return

    User = get_user_model()

    employee, employee_created = User.objects.get_or_create(
        username="coach@moderation.app",
        defaults={
            "email": "coach@moderation.app",
            "first_name": "Coach",
            "last_name": "Mira",
            "role": User.Roles.EMPLOYEE,
            "is_staff": True,
        },
    )
    if employee_created:
        employee.set_password("employee-demo")
        employee.save()

    customer, customer_created = User.objects.get_or_create(
        username="jordan@moderation.app",
        defaults={
            "email": "jordan@moderation.app",
            "first_name": "Jordan",
            "last_name": "Reed",
            "role": User.Roles.CUSTOMER,
        },
    )
    if customer_created:
        customer.set_password("customer-demo")
        customer.save()

    HealthProfile.objects.get_or_create(
        user=customer,
        defaults={
            "daily_recommendation": "Take a 20-minute walk, prep one balanced meal, and log water before dinner.",
            "wellness_focus": "Consistency over intensity",
            "steps": 7420,
            "water_oz": 56,
            "sleep_hours": 7.2,
            "workouts_per_week": 3,
        },
    )
    HealthProfile.objects.get_or_create(
        user=employee,
        defaults={
            "daily_recommendation": "Review one customer plan and add one analytics-aware recommendation today.",
            "wellness_focus": "Supportive accountability",
            "steps": 5100,
            "water_oz": 42,
            "sleep_hours": 6.8,
            "workouts_per_week": 2,
        },
    )

    if not customer.health_goals.exists():
        for index, goal in enumerate([
            "Improve weekly consistency with workouts",
            "Build better meal rhythm",
            "Increase sleep and hydration",
        ]):
            HealthGoal.objects.create(user=customer, title=goal, sort_order=index)

    if not customer.meal_entries.exists():
        MealEntry.objects.create(user=customer, meal_name="Greek yogurt bowl", time_of_day=MealEntry.MealTimes.BREAKFAST, notes="Protein, berries, granola", calories=420)
        MealEntry.objects.create(user=customer, meal_name="Chicken rice plate", time_of_day=MealEntry.MealTimes.LUNCH, notes="Chicken, brown rice, greens", calories=610)

    if not Recommendation.objects.exists():
        Recommendation.objects.create(
            title="Balanced breakfast prompt",
            category=Recommendation.Categories.DIET,
            guidance="Begin with protein, fiber, and water to create a steadier start for the day.",
            analytics_focus="meal consistency",
            created_by=employee,
        )
        Recommendation.objects.create(
            title="Low-pressure movement plan",
            category=Recommendation.Categories.EXERCISE,
            guidance="Aim for a walk after meals and one focused workout block during the week.",
            analytics_focus="movement baseline",
            created_by=employee,
        )
        Recommendation.objects.create(
            title="Recovery anchor",
            category=Recommendation.Categories.WELLNESS,
            guidance="Protect hydration and sleep first when stress is high.",
            analytics_focus="sleep and hydration",
            created_by=employee,
        )

    if not customer.chat_messages.exists():
        ChatMessage.objects.create(
            user=customer,
            channel=ChatMessage.Channels.CHATBOT,
            author_name="Moderation Bot",
            message="Hello. I can help with nutrition, exercise, and wellness questions using your saved health data.",
            is_machine_generated=True,
        )
        ChatMessage.objects.create(
            user=customer,
            channel=ChatMessage.Channels.COACH,
            author_name="Coach Mira",
            message="I am here to turn your health goals into a realistic weekly plan.",
            is_machine_generated=True,
        )