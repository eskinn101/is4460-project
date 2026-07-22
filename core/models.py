from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
	class Roles(models.TextChoices):
		CUSTOMER = "customer", "Customer"
		EMPLOYEE = "employee", "Employee"

	email = models.EmailField(unique=True)
	role = models.CharField(max_length=20, choices=Roles.choices, default=Roles.CUSTOMER)

	def __str__(self):
		return self.get_full_name() or self.username


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
