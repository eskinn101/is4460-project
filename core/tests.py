from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import HealthGoal, HealthProfile, Recommendation


class AppStartupTests(TestCase):
	"""Guards against the app failing to boot (bad imports, missing migrations, broken URLs)."""

	def test_system_check_passes(self):
		call_command("check")

	def test_no_missing_migrations(self):
		try:
			call_command("makemigrations", check=True, dry_run=True)
		except SystemExit:
			self.fail("Model changes are missing a migration file. Run `python manage.py makemigrations`.")

	def test_home_page_loads_for_anonymous_visitor(self):
		response = self.client.get(reverse("home"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Continue as customer")
		self.assertContains(response, "Continue as employee")


class LoginFlowTests(TestCase):
	"""Confirms the seeded customer, employee, and HR/superuser accounts can always log in."""

	def setUp(self):
		self.User = get_user_model()

	def test_seeded_customer_can_log_in(self):
		response = self.client.post(
			reverse("home"),
			{
				"customer-role": self.User.Roles.CUSTOMER,
				"customer-email": "jordan@moderation.app",
				"customer-password": "customer-demo",
			},
		)

		self.assertRedirects(response, reverse("customer_dashboard"))
		self.assertTrue(response.wsgi_request.user.is_authenticated)

	def test_seeded_employee_can_log_in(self):
		response = self.client.post(
			reverse("home"),
			{
				"employee-role": self.User.Roles.EMPLOYEE,
				"employee-email": "coach@moderation.app",
				"employee-password": "employee-demo",
			},
		)

		self.assertRedirects(response, reverse("employee_dashboard"))
		self.assertTrue(response.wsgi_request.user.is_authenticated)

	def test_seeded_hr_superuser_can_log_in(self):
		response = self.client.post(
			reverse("home"),
			{
				"employee-role": self.User.Roles.HR,
				"employee-email": "fake@gmail",
				"employee-password": "fake12345",
			},
		)

		self.assertRedirects(response, reverse("employee_dashboard"))
		user = response.wsgi_request.user
		self.assertTrue(user.is_authenticated)
		self.assertTrue(user.is_superuser)

	def test_wrong_password_is_rejected(self):
		response = self.client.post(
			reverse("home"),
			{
				"customer-role": self.User.Roles.CUSTOMER,
				"customer-email": "jordan@moderation.app",
				"customer-password": "not-the-right-password",
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Invalid login details.")
		self.assertFalse(response.wsgi_request.user.is_authenticated)

	def test_customer_credentials_rejected_on_employee_form(self):
		response = self.client.post(
			reverse("home"),
			{
				"employee-role": self.User.Roles.EMPLOYEE,
				"employee-email": "jordan@moderation.app",
				"employee-password": "customer-demo",
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Invalid login details.")
		self.assertFalse(response.wsgi_request.user.is_authenticated)


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

	def test_seeded_hr_account_exists_with_superuser_access(self):
		hr = self.User.objects.get(username="fake@gmail")
		self.assertEqual(hr.email, "fake@gmail")
		self.assertEqual(hr.role, self.User.Roles.HR)
		self.assertTrue(hr.is_staff)
		self.assertTrue(hr.is_superuser)

	def test_customer_registration_creates_account_and_redirects_to_customer_dashboard(self):
		response = self.client.post(
			reverse("account"),
			{
				"customer-account_type": self.User.Roles.CUSTOMER,
				"customer-first_name": "Jordan",
				"customer-last_name": "Lee",
				"customer-email": "newcustomer@example.com",
				"customer-password": "strong-pass-123",
				"customer-confirm_password": "strong-pass-123",
			},
		)

		self.assertEqual(response.status_code, 302)
		self.assertRedirects(response, reverse("customer_dashboard"))
		self.assertTrue(self.User.objects.filter(email="newcustomer@example.com", role=self.User.Roles.CUSTOMER).exists())

	def test_employee_registration_creates_account_and_redirects_to_employee_dashboard(self):
		response = self.client.post(
			reverse("account"),
			{
				"employee-account_type": self.User.Roles.EMPLOYEE,
				"employee-first_name": "Coach",
				"employee-last_name": "Mira",
				"employee-email": "newemployee@example.com",
				"employee-date_of_birth": "1992-08-14",
				"employee-password": "strong-pass-123",
				"employee-confirm_password": "strong-pass-123",
			},
		)

		self.assertEqual(response.status_code, 302)
		self.assertRedirects(response, reverse("employee_dashboard"))
		self.assertTrue(self.User.objects.filter(email="newemployee@example.com", role=self.User.Roles.EMPLOYEE).exists())
		employee = self.User.objects.get(email="newemployee@example.com", role=self.User.Roles.EMPLOYEE)
		self.assertEqual(str(employee.date_of_birth), "1992-08-14")
		self.assertTrue(employee.is_staff)
		self.assertFalse(employee.is_superuser)

	def test_hr_registration_creates_superuser_and_redirects_to_employee_dashboard(self):
		response = self.client.post(
			reverse("account"),
			{
				"employee-account_type": self.User.Roles.HR,
				"employee-first_name": "Casey",
				"employee-last_name": "Rivera",
				"employee-email": "hrnew@example.com",
				"employee-date_of_birth": "1988-02-11",
				"employee-password": "strong-pass-123",
				"employee-confirm_password": "strong-pass-123",
			},
		)

		self.assertEqual(response.status_code, 302)
		self.assertRedirects(response, reverse("employee_dashboard"))
		self.assertTrue(self.User.objects.filter(email="hrnew@example.com", role=self.User.Roles.HR).exists())
		hr = self.User.objects.get(email="hrnew@example.com", role=self.User.Roles.HR)
		self.assertEqual(str(hr.date_of_birth), "1988-02-11")
		self.assertTrue(hr.is_staff)
		self.assertTrue(hr.is_superuser)

	def test_employee_registration_requires_birthday(self):
		response = self.client.post(
			reverse("account"),
			{
				"employee-account_type": self.User.Roles.EMPLOYEE,
				"employee-first_name": "Coach",
				"employee-last_name": "Mira",
				"employee-email": "employeewithoutdob@example.com",
				"employee-password": "strong-pass-123",
				"employee-confirm_password": "strong-pass-123",
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Birthday is required for employee accounts.")
		self.assertFalse(self.User.objects.filter(email="employeewithoutdob@example.com").exists())

	def test_hr_can_access_customer_and_employee_pages(self):
		hr = self.User.objects.create_user(
			username="hr-access@example.com",
			email="hr-access@example.com",
			password="test-pass-123",
			role=self.User.Roles.HR,
			is_staff=True,
			is_superuser=True,
		)

		self.client.force_login(hr)

		self.assertEqual(self.client.get(reverse("employee_dashboard")).status_code, 200)
		self.assertEqual(self.client.get(reverse("wellness_partners")).status_code, 200)


class WellnessPartnersPageTests(TestCase):
	def setUp(self):
		self.User = get_user_model()
		self.customer = self.User.objects.create_user(
			username="customer@example.com",
			email="customer@example.com",
			password="test-pass-123",
			role=self.User.Roles.CUSTOMER,
		)

	def test_anonymous_users_are_redirected_from_wellness_partners_page(self):
		response = self.client.get(reverse("wellness_partners"))

		self.assertEqual(response.status_code, 302)
		self.assertRedirects(response, "/?next=/wellness-partners/")

	def test_customer_users_can_view_wellness_partners_page(self):
		self.client.force_login(self.customer)
		response = self.client.get(reverse("wellness_partners"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Wellness Partners")
		self.assertContains(response, "Fresh Bowl Kitchen")
		self.assertContains(response, "Exclusive Partner Rewards")
