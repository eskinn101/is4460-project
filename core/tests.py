from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import HealthGoal, HealthProfile, Recommendation


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


class AccountPageRegistrationTests(TestCase):
	def setUp(self):
		self.User = get_user_model()

	def test_customer_registration_creates_account_and_redirects_to_customer_dashboard(self):
		response = self.client.post(
			reverse("account"),
			{
				"account_type": self.User.Roles.CUSTOMER,
				"first_name": "Jordan",
				"last_name": "Lee",
				"email": "newcustomer@example.com",
				"password": "strong-pass-123",
				"confirm_password": "strong-pass-123",
			},
		)

		self.assertEqual(response.status_code, 302)
		self.assertRedirects(response, reverse("customer_dashboard"))
		self.assertTrue(self.User.objects.filter(email="newcustomer@example.com", role=self.User.Roles.CUSTOMER).exists())

	def test_employee_registration_creates_account_and_redirects_to_employee_dashboard(self):
		response = self.client.post(
			reverse("account"),
			{
				"account_type": self.User.Roles.EMPLOYEE,
				"first_name": "Coach",
				"last_name": "Mira",
				"email": "newemployee@example.com",
				"password": "strong-pass-123",
				"confirm_password": "strong-pass-123",
			},
		)

		self.assertEqual(response.status_code, 302)
		self.assertRedirects(response, reverse("employee_dashboard"))
		self.assertTrue(self.User.objects.filter(email="newemployee@example.com", role=self.User.Roles.EMPLOYEE).exists())
