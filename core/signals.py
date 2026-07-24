from django.contrib.auth import get_user_model
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from .models import ChatMessage, HealthGoal, HealthProfile, MealEntry, Recommendation


def _ensure_customer_profile(user, profile_defaults):
    profile, _ = HealthProfile.objects.get_or_create(user=user, defaults=profile_defaults)
    return profile


def _ensure_customer_goals(user, goals):
    if user.health_goals.exists():
        return
    for index, goal in enumerate(goals):
        HealthGoal.objects.create(user=user, title=goal, sort_order=index)


def _ensure_customer_meals(user, meals):
    if user.meal_entries.exists():
        return
    for meal in meals:
        MealEntry.objects.create(user=user, **meal)


def _ensure_customer_chat_starters(user, prompts):
    if user.chat_messages.exists():
        return

    ChatMessage.objects.create(
        user=user,
        channel=ChatMessage.Channels.CHATBOT,
        author_name="Moderation Bot",
        message="Hello. I can use your profile, meals, goals, and recommendation library data to provide practical guidance.",
        is_machine_generated=True,
    )
    ChatMessage.objects.create(
        user=user,
        channel=ChatMessage.Channels.COACH,
        author_name="Coach Mira",
        message="I am here to build a realistic weekly plan based on your data and goals.",
        is_machine_generated=True,
    )
    for prompt in prompts:
        ChatMessage.objects.create(
            user=user,
            channel=ChatMessage.Channels.CHATBOT,
            author_name="You",
            message=prompt,
            is_machine_generated=False,
        )


def _ensure_demo_customer(User, *, username, first_name, last_name, profile_defaults, goals, meals, prompts):
    customer, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email": username,
            "first_name": first_name,
            "last_name": last_name,
            "role": User.Roles.CUSTOMER,
        },
    )
    if created:
        customer.set_password("customer-demo")
        customer.save()

    _ensure_customer_profile(customer, profile_defaults)
    _ensure_customer_goals(customer, goals)
    _ensure_customer_meals(customer, meals)
    _ensure_customer_chat_starters(customer, prompts)
    return customer


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

    hr, hr_created = User.objects.get_or_create(
        username="fake@gmail",
        defaults={
            "email": "fake@gmail",
            "first_name": "Human",
            "last_name": "Resources",
            "role": User.Roles.HR,
            "is_staff": True,
            "is_superuser": True,
        },
    )
    hr.email = "fake@gmail"
    hr.first_name = "Human"
    hr.last_name = "Resources"
    hr.role = User.Roles.HR
    hr.is_staff = True
    hr.is_superuser = True
    hr.set_password("fake12345")
    hr.save()

    customer = _ensure_demo_customer(
        User,
        username="jordan@moderation.app",
        first_name="Jordan",
        last_name="Reed",
        profile_defaults={
            "daily_recommendation": "Take a 20-minute walk, prep one balanced meal, and log water before dinner.",
            "wellness_focus": "Consistency over intensity",
            "steps": 7420,
            "water_oz": 56,
            "sleep_hours": 7.2,
            "workouts_per_week": 3,
        },
        goals=[
            "Improve weekly consistency with workouts",
            "Build better meal rhythm",
            "Increase sleep and hydration",
        ],
        meals=[
            {"meal_name": "Greek yogurt bowl", "time_of_day": MealEntry.MealTimes.BREAKFAST, "notes": "Protein, berries, granola", "calories": 420},
            {"meal_name": "Chicken rice plate", "time_of_day": MealEntry.MealTimes.LUNCH, "notes": "Chicken, brown rice, greens", "calories": 610},
        ],
        prompts=[
            "I want to improve energy in the afternoon without extra caffeine.",
            "Can you suggest a high-protein dinner that still fits fat-loss goals?",
        ],
    )

    _ensure_demo_customer(
        User,
        username="riley.fit@moderation.app",
        first_name="Riley",
        last_name="Nguyen",
        profile_defaults={
            "daily_recommendation": "Prioritize strength work three days weekly and increase protein at breakfast.",
            "wellness_focus": "Muscle gain while reducing body fat",
            "steps": 8800,
            "water_oz": 68,
            "sleep_hours": 6.6,
            "workouts_per_week": 4,
        },
        goals=[
            "Gain lean muscle while dropping 4 pounds of fat",
            "Hit 120g protein at least 5 days each week",
            "Sleep at least 7 hours on weeknights",
        ],
        meals=[
            {"meal_name": "Egg white scramble", "time_of_day": MealEntry.MealTimes.BREAKFAST, "notes": "Egg whites, spinach, feta", "calories": 360},
            {"meal_name": "Salmon quinoa bowl", "time_of_day": MealEntry.MealTimes.DINNER, "notes": "Salmon, quinoa, broccoli", "calories": 690},
        ],
        prompts=[
            "My goal is to gain muscle while losing fat over the next 8 weeks.",
            "How should I structure meals on lifting days vs rest days?",
        ],
    )

    _ensure_demo_customer(
        User,
        username="taylor.recover@moderation.app",
        first_name="Taylor",
        last_name="Brooks",
        profile_defaults={
            "daily_recommendation": "Anchor hydration early and add low-impact evening movement.",
            "wellness_focus": "Recovery and stress reduction",
            "steps": 5100,
            "water_oz": 38,
            "sleep_hours": 5.9,
            "workouts_per_week": 1,
        },
        goals=[
            "Increase daily water intake to 80 oz",
            "Improve sleep quality and consistency",
            "Build a low-stress movement routine",
        ],
        meals=[
            {"meal_name": "Turkey wrap", "time_of_day": MealEntry.MealTimes.LUNCH, "notes": "Turkey, whole-grain wrap, greens", "calories": 480},
            {"meal_name": "Greek yogurt + banana", "time_of_day": MealEntry.MealTimes.SNACK, "notes": "High-protein snack", "calories": 260},
        ],
        prompts=[
            "I am sleeping poorly and craving sugar at night. What should I change first?",
            "Can you give me a realistic hydration routine for work days?",
        ],
    )

    _ensure_demo_customer(
        User,
        username="casey.endurance@moderation.app",
        first_name="Casey",
        last_name="Lopez",
        profile_defaults={
            "daily_recommendation": "Balance endurance sessions with recovery meals and hydration checks.",
            "wellness_focus": "Endurance performance",
            "steps": 11600,
            "water_oz": 74,
            "sleep_hours": 7.4,
            "workouts_per_week": 5,
        },
        goals=[
            "Improve 5K pace by 45 seconds",
            "Fuel long runs with better carb timing",
            "Keep recovery soreness below 2 days",
        ],
        meals=[
            {"meal_name": "Overnight oats", "time_of_day": MealEntry.MealTimes.BREAKFAST, "notes": "Oats, berries, chia", "calories": 430},
            {"meal_name": "Chicken pasta", "time_of_day": MealEntry.MealTimes.DINNER, "notes": "Chicken, whole-wheat pasta, tomato sauce", "calories": 720},
        ],
        prompts=[
            "What should I eat 90 minutes before a run?",
            "How do I recover better after interval workouts?",
        ],
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
