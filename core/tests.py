from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import HealthGoal, HealthProfile, Recommendation, Workout


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


class HRAdminPermissionsTests(TestCase):
	"""Confirms the HR/superuser tier can edit and delete any account; other tiers cannot."""

	def setUp(self):
		self.User = get_user_model()
		self.hr = self.User.objects.create_user(
			username="hr-admin@example.com",
			email="hr-admin@example.com",
			password="test-pass-123",
			role=self.User.Roles.HR,
			is_staff=True,
			is_superuser=True,
		)
		self.employee = self.User.objects.create_user(
			username="coach-plain@example.com",
			email="coach-plain@example.com",
			password="test-pass-123",
			role=self.User.Roles.EMPLOYEE,
			is_staff=True,
		)
		self.target = self.User.objects.create_user(
			username="editable-user@example.com",
			email="editable-user@example.com",
			password="test-pass-123",
			role=self.User.Roles.CUSTOMER,
			first_name="Old",
		)

	def test_hr_can_edit_another_users_account(self):
		self.client.force_login(self.hr)
		change_url = reverse("admin:core_user_change", args=[self.target.pk])

		response = self.client.post(
			change_url,
			{
				"username": self.target.username,
				"first_name": "Updated",
				"last_name": self.target.last_name,
				"email": self.target.email,
				"role": self.User.Roles.CUSTOMER,
				"date_joined_0": self.target.date_joined.date().isoformat(),
				"date_joined_1": self.target.date_joined.time().strftime("%H:%M:%S"),
			},
		)

		self.assertEqual(response.status_code, 302)
		self.target.refresh_from_db()
		self.assertEqual(self.target.first_name, "Updated")

	def test_hr_can_delete_another_users_account(self):
		self.client.force_login(self.hr)
		delete_url = reverse("admin:core_user_delete", args=[self.target.pk])

		response = self.client.post(delete_url, {"post": "yes"})

		self.assertEqual(response.status_code, 302)
		self.assertFalse(self.User.objects.filter(pk=self.target.pk).exists())

	def test_plain_employee_cannot_edit_or_delete_accounts(self):
		self.client.force_login(self.employee)

		change_url = reverse("admin:core_user_change", args=[self.target.pk])
		delete_url = reverse("admin:core_user_delete", args=[self.target.pk])

		self.assertEqual(self.client.get(change_url).status_code, 403)
		self.assertEqual(self.client.get(delete_url).status_code, 403)
		self.assertTrue(self.User.objects.filter(pk=self.target.pk).exists())


class AccountManagementPageTests(TestCase):
	"""Covers the in-app Manage Accounts page (as opposed to Django's /admin/)."""

	def setUp(self):
		self.User = get_user_model()
		self.hr = self.User.objects.create_user(
			username="hr-manager@example.com",
			email="hr-manager@example.com",
			password="test-pass-123",
			role=self.User.Roles.HR,
			is_staff=True,
			is_superuser=True,
		)
		self.employee = self.User.objects.create_user(
			username="coach-plain@example.com",
			email="coach-plain@example.com",
			password="test-pass-123",
			role=self.User.Roles.EMPLOYEE,
			is_staff=True,
		)
		self.customer = self.User.objects.create_user(
			username="jane@example.com",
			email="jane@example.com",
			password="test-pass-123",
			role=self.User.Roles.CUSTOMER,
			first_name="Jane",
		)

	def test_hr_can_view_account_management_page(self):
		self.client.force_login(self.hr)

		response = self.client.get(reverse("account_management"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "jane@example.com")
		self.assertContains(response, "coach-plain@example.com")

	def test_hr_can_edit_and_promote_an_account(self):
		self.client.force_login(self.hr)

		response = self.client.post(
			reverse("account_edit", args=[self.customer.pk]),
			{
				"first_name": "Janet",
				"last_name": self.customer.last_name,
				"email": self.customer.email,
				"role": self.User.Roles.EMPLOYEE,
			},
		)

		self.assertRedirects(response, reverse("account_management"))
		self.customer.refresh_from_db()
		self.assertEqual(self.customer.first_name, "Janet")
		self.assertEqual(self.customer.role, self.User.Roles.EMPLOYEE)
		self.assertTrue(self.customer.is_staff)
		self.assertFalse(self.customer.is_superuser)

	def test_hr_can_delete_an_account(self):
		self.client.force_login(self.hr)

		response = self.client.post(reverse("account_delete", args=[self.customer.pk]))

		self.assertRedirects(response, reverse("account_management"))
		self.assertFalse(self.User.objects.filter(pk=self.customer.pk).exists())

	def test_hr_cannot_delete_their_own_account(self):
		self.client.force_login(self.hr)

		response = self.client.post(reverse("account_delete", args=[self.hr.pk]))

		self.assertRedirects(response, reverse("account_management"))
		self.assertTrue(self.User.objects.filter(pk=self.hr.pk).exists())

	def test_non_superuser_accounts_are_forbidden(self):
		for account in (self.employee, self.customer):
			self.client.force_login(account)

			self.assertEqual(self.client.get(reverse("account_management")).status_code, 403)
			self.assertEqual(self.client.get(reverse("account_edit", args=[self.hr.pk])).status_code, 403)
			self.assertEqual(self.client.post(reverse("account_delete", args=[self.hr.pk])).status_code, 403)
			self.client.logout()


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


class WorkoutTrackingTests(TestCase):
	def setUp(self):
		self.User = get_user_model()
		self.customer = self.User.objects.create_user(
			username="workout-customer@example.com",
			email="workout-customer@example.com",
			password="test-pass-123",
			role=self.User.Roles.CUSTOMER,
		)
		HealthProfile.objects.create(
			user=self.customer,
			daily_recommendation="Keep moving steadily.",
			wellness_focus="Consistency",
			steps=5000,
			water_oz=64,
			sleep_hours=7.0,
			workouts_per_week=3,
		)

	def test_authenticated_customer_can_log_and_view_workout(self):
		self.client.force_login(self.customer)
		response = self.client.post(
			reverse("workout_create"),
			{
				"workout_type": Workout.WorkoutTypes.STRENGTH_TRAINING,
				"workout_date": "2026-07-22",
				"duration_minutes": 45,
				"intensity": Workout.IntensityChoices.MODERATE,
				"notes": "Upper-body session",
			},
		)

		self.assertEqual(response.status_code, 302)
		self.assertRedirects(response, reverse("health"))
		self.assertTrue(Workout.objects.filter(user=self.customer).exists())
		self.assertEqual(Workout.objects.get(user=self.customer).duration_minutes, 45)

		health_response = self.client.get(reverse("health"))
		self.assertContains(health_response, "Recent Workouts")
		self.assertContains(health_response, "Strength Training")
		self.assertContains(health_response, "Upper-body session")

	def test_invalid_duration_shows_validation_error(self):
		self.client.force_login(self.customer)
		response = self.client.post(
			reverse("workout_create"),
			{
				"workout_type": Workout.WorkoutTypes.WALKING,
				"workout_date": "2026-07-22",
				"duration_minutes": 0,
				"intensity": Workout.IntensityChoices.LIGHT,
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Duration must be greater than 0.")
		self.assertFalse(Workout.objects.exists())

	def test_customer_cannot_delete_another_customers_workout(self):
		other_customer = self.User.objects.create_user(
			username="other@example.com",
			email="other@example.com",
			password="test-pass-123",
			role=self.User.Roles.CUSTOMER,
		)
		workout = Workout.objects.create(
			user=other_customer,
			workout_type=Workout.WorkoutTypes.RUNNING,
			duration_minutes=30,
			workout_date="2026-07-22",
			intensity=Workout.IntensityChoices.HIGH,
		)

		self.client.force_login(self.customer)
		response = self.client.post(reverse("workout_delete", args=[workout.pk]))

		self.assertEqual(response.status_code, 404)
		self.assertTrue(Workout.objects.filter(pk=workout.pk).exists())

	def test_anonymous_users_are_redirected_from_workout_create(self):
		response = self.client.post(reverse("workout_create"), {"workout_type": Workout.WorkoutTypes.WALKING, "duration_minutes": 20})

		self.assertEqual(response.status_code, 302)
		self.assertRedirects(response, "/?next=/workouts/create/")
