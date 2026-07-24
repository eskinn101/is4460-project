from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import ChatMessage, HealthGoal, HealthProfile, Recommendation


class CustomerSummaryApiTests(TestCase):
	def setUp(self):
		self.User = get_user_model()
		self.customer = self.User.objects.create_user(
			username="customer@example.com",
			email="customer@example.com",
			password="test-pass-123",
			role=self.User.Roles.CUSTOMER,
		)
		HealthProfile.objects.create(
			user=self.customer,
			daily_recommendation="Walk after lunch and log water before dinner.",
			wellness_focus="Consistency over intensity",
			steps=9100,
			water_oz=72,
			sleep_hours=7.5,
			workouts_per_week=4,
		)
		HealthGoal.objects.create(user=self.customer, title="Keep workouts regular", sort_order=0)
		Recommendation.objects.create(
			title="Protein-forward breakfast",
			category=Recommendation.Categories.DIET,
			guidance="Start with protein, fiber, and water to support steadier energy.",
			analytics_focus="meal consistency",
		)

	def test_customer_summary_api_returns_merged_health_data(self):
		self.client.force_login(self.customer)

		response = self.client.get(reverse("customer_summary_api"))

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload["profile"]["steps"], 9100)
		self.assertEqual(payload["goals"], ["Keep workouts regular"])
		self.assertEqual(payload["recommendations"]["primary"]["title"], "Protein-forward breakfast")
		self.assertIn("consistency_score", payload["analytics"])

	def test_customer_chat_creates_goal_and_generates_machine_reply(self):
		self.client.force_login(self.customer)
		before_goals = self.customer.health_goals.count()

		response = self.client.post(
			reverse("chat"),
			data={"chatbot-channel": "chatbot", "chatbot-message": "My goal is to gain muscle while losing fat this quarter."},
		)

		self.assertEqual(response.status_code, 302)
		self.customer.refresh_from_db()
		self.assertEqual(self.customer.health_goals.count(), before_goals + 1)
		self.assertTrue(self.customer.health_goals.filter(title="Gain muscle, lose fat").exists())

		machine_reply = ChatMessage.objects.filter(
			user=self.customer,
			is_machine_generated=True,
			channel=ChatMessage.Channels.CHATBOT,
		).order_by("-id").first()
		self.assertIsNotNone(machine_reply)
		self.assertNotIn("You mentioned:", machine_reply.message)
		self.assertNotIn("Recommendation library match:", machine_reply.message)

	def test_customer_chat_updates_and_deletes_goal_from_intent(self):
		self.client.force_login(self.customer)
		existing_goal = self.customer.health_goals.first()

		update_response = self.client.post(
			reverse("chat"),
			data={"chatbot-channel": "chatbot", "chatbot-message": "Change my goal from Keep workouts regular to Walk after dinner four nights each week."},
		)
		self.assertEqual(update_response.status_code, 302)
		existing_goal.refresh_from_db()
		self.assertEqual(existing_goal.title, "Walk after dinner four nights")

		delete_response = self.client.post(
			reverse("chat"),
			data={"chatbot-channel": "chatbot", "chatbot-message": "Remove goal Walk after dinner four nights."},
		)
		self.assertEqual(delete_response.status_code, 302)
		self.assertFalse(self.customer.health_goals.filter(title="Walk after dinner four nights").exists())
