from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
	class Roles(models.TextChoices):
		CUSTOMER = "customer", "Customer"
		EMPLOYEE = "employee", "Coach"
		HR = "hr", "Human Resources"

		@classmethod
		def employee_roles(cls):
			return (cls.EMPLOYEE, cls.HR)

		@classmethod
		def employee_choices(cls):
			return ((cls.EMPLOYEE, "Coach"), (cls.HR, "Human Resources"))

	email = models.EmailField(unique=True)
	role = models.CharField(max_length=20, choices=Roles.choices, default=Roles.CUSTOMER)
	date_of_birth = models.DateField(null=True, blank=True)
	phone_number = models.CharField(max_length=20, blank=True)
	city = models.CharField(max_length=120, blank=True)
	state = models.CharField(max_length=120, blank=True)

	def __str__(self):
		return self.get_full_name() or self.username


class Workout(models.Model):
	class WorkoutTypes(models.TextChoices):
		WALKING = "Walking", "Walking"
		RUNNING = "Running", "Running"
		STRENGTH_TRAINING = "Strength Training", "Strength Training"
		CYCLING = "Cycling", "Cycling"
		SWIMMING = "Swimming", "Swimming"
		YOGA = "Yoga", "Yoga"
		HIIT = "HIIT", "HIIT"
		SPORTS = "Sports", "Sports"
		OTHER = "Other", "Other"

	class IntensityChoices(models.TextChoices):
		LIGHT = "Light", "Light"
		MODERATE = "Moderate", "Moderate"
		HIGH = "High", "High"

	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="workouts")
	workout_type = models.CharField(max_length=40, choices=WorkoutTypes.choices)
	duration_minutes = models.PositiveIntegerField()
	workout_date = models.DateField(default=timezone.localdate)
	intensity = models.CharField(max_length=20, choices=IntensityChoices.choices)
	notes = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-workout_date", "-created_at"]

	def __str__(self):
		return f"{self.workout_type} for {self.duration_minutes} minutes"


class HealthProfile(models.Model):
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="health_profile")
	daily_recommendation = models.TextField()
	wellness_focus = models.CharField(max_length=255)
	steps = models.PositiveIntegerField(default=0)
	water_oz = models.PositiveIntegerField(default=0)
	sleep_hours = models.DecimalField(max_digits=4, decimal_places=1, default=0)
	workouts_per_week = models.PositiveIntegerField(default=0)
	updated_at = models.DateTimeField(auto_now=True)


class HealthGoal(models.Model):
	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="health_goals")
	title = models.CharField(max_length=255)
	sort_order = models.PositiveIntegerField(default=0)

	class Meta:
		ordering = ["sort_order", "id"]


class Recommendation(models.Model):
	class Categories(models.TextChoices):
		DIET = "Diet", "Diet"
		EXERCISE = "Exercise", "Exercise"
		WELLNESS = "Wellness", "Wellness"

	title = models.CharField(max_length=255)
	category = models.CharField(max_length=20, choices=Categories.choices)
	guidance = models.TextField()
	analytics_focus = models.CharField(max_length=255, blank=True)
	created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_recommendations")
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]


class RecommendationDataFile(models.Model):
	file = models.FileField(upload_to="recommendation_uploads/")
	original_name = models.CharField(max_length=255)
	imported_rows = models.PositiveIntegerField(default=0)
	uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploaded_recommendation_files")
	uploaded_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-uploaded_at", "-id"]

	def __str__(self):
		return self.original_name


class BotBehaviorConfig(models.Model):
	instructions = models.TextField(
		default=(
			"Keep guidance practical, supportive, and non-judgmental. "
			"Use only the supplied customer profile and recommendation data. "
			"Do not provide medical diagnosis or treatment advice."
		)
	)
	updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="updated_bot_behavior_configs")
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return "Bot Behavior Configuration"


class CustomerBotBehaviorOverride(models.Model):
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="bot_behavior_override")
	instructions = models.TextField(blank=True)
	updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="updated_customer_bot_behavior_overrides")
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["user_id"]

	def __str__(self):
		return f"Behavior override for {self.user}"


class BotBehaviorRevision(models.Model):
	class Scopes(models.TextChoices):
		GLOBAL = "global", "Global"
		CUSTOMER = "customer", "Customer"

	scope = models.CharField(max_length=20, choices=Scopes.choices)
	customer = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="bot_behavior_revisions")
	instructions = models.TextField()
	updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_bot_behavior_revisions")
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at", "-id"]

	def __str__(self):
		if self.scope == self.Scopes.CUSTOMER and self.customer:
			return f"Customer behavior revision for {self.customer}"
		return "Global behavior revision"


class MealEntry(models.Model):
	class MealTimes(models.TextChoices):
		BREAKFAST = "Breakfast", "Breakfast"
		LUNCH = "Lunch", "Lunch"
		DINNER = "Dinner", "Dinner"
		SNACK = "Snack", "Snack"

	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="meal_entries")
	meal_name = models.CharField(max_length=255)
	time_of_day = models.CharField(max_length=20, choices=MealTimes.choices)
	calories = models.PositiveIntegerField(default=0)
	notes = models.TextField(blank=True)
	consumed_at = models.DateTimeField(default=timezone.now)

	class Meta:
		ordering = ["-consumed_at"]


class ChatMessage(models.Model):
	class Channels(models.TextChoices):
		CHATBOT = "chatbot", "Chatbot"
		COACH = "coach", "Coach"

	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_messages")
	channel = models.CharField(max_length=20, choices=Channels.choices)
	author_name = models.CharField(max_length=255)
	message = models.TextField()
	is_machine_generated = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["created_at", "id"]
