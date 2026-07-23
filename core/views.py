from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import AccountManagementForm, ChatForm, CustomerLoginForm, CustomerRegistrationForm, EmployeeLoginForm, EmployeeRegistrationForm, HealthProfileForm, MealEntryForm, ProfileForm, RecommendationForm, WorkoutForm
from .models import ChatMessage, HealthGoal, HealthProfile, Recommendation, User, Workout
from .services import build_ai_guidance, build_chat_response, customer_analytics, customer_summary_payload, relevant_recommendations


PARTNER_DATA = [
	{
		"slug": "fresh-bowl-kitchen",
		"name": "Fresh Bowl Kitchen",
		"category": "Restaurant",
		"category_key": "restaurants",
		"description": "A bright, protein-forward spot serving balanced bowls and hearty salads that fit busy routines.",
		"location": "2.4 mi away • Midtown",
		"distance": "2.4 mi",
		"rating": 4.8,
		"match_score": 94,
		"recommendation_reason": "Recommended because its high-protein meals align with your nutrition goals and recent workout activity.",
		"promotion": "20% off a high-protein bowl this week",
		"is_featured": True,
		"is_nearby": True,
		"tags": ["restaurants", "nearby", "discounts"],
		"offers": [
			{"name": "Grilled Chicken Power Bowl", "calories": "610 kcal", "protein": "42g", "carbs": "58g", "fat": "18g"},
			{"name": "Plant-Based Protein Smoothie", "calories": "340 kcal", "protein": "24g", "carbs": "41g", "fat": "10g"},
		],
		"services": [],
		"detail_blurb": "This partner is known for flexible meal ordering and nutrition-friendly menus that support steady, practical progress.",
	},
	{
		"slug": "core-strength-studio",
		"name": "Core Strength Studio",
		"category": "Gym",
		"category_key": "gyms",
		"description": "A welcoming strength and mobility studio that offers beginner-friendly coaching and recovery support.",
		"location": "4.1 mi away • North Loop",
		"distance": "4.1 mi",
		"rating": 4.7,
		"match_score": 91,
		"recommendation_reason": "Recommended because your recent activity suggests a strength-focused plan would complement your goals.",
		"promotion": "Free seven-day gym trial for new members",
		"is_featured": True,
		"is_nearby": False,
		"tags": ["gyms", "discounts"],
		"offers": [
			{"name": "Beginner Strength Training Session", "service_type": "Coach-led circuit", "duration": "45 min", "difficulty": "Beginner"},
			{"name": "Mobility Recovery Flow", "service_type": "Recovery class", "duration": "30 min", "difficulty": "All levels"},
		],
		"services": [],
		"detail_blurb": "The studio pairs guided coaching with approachable sessions that fit recurring wellness routines.",
	},
	{
		"slug": "balance-meal-prep",
		"name": "Balance Meal Prep",
		"category": "Meal Prep",
		"category_key": "meal-prep",
		"description": "Weekly meal prep bundles built around protein balance, portion control, and convenient delivery.",
		"location": "1.8 mi away • Riverfront",
		"distance": "1.8 mi",
		"rating": 4.9,
		"match_score": 96,
		"recommendation_reason": "Recommended because its meal bundles support your balanced nutrition and time-saving routine.",
		"promotion": "Buy one weekly plan, get a second half off",
		"is_featured": True,
		"is_nearby": True,
		"tags": ["meal-prep", "nearby", "discounts"],
		"offers": [
			{"name": "Protein Power Bundle", "calories": "760 kcal", "protein": "55g", "carbs": "72g", "fat": "24g"},
			{"name": "Plant Recovery Box", "calories": "680 kcal", "protein": "31g", "carbs": "80g", "fat": "20g"},
		],
		"services": [],
		"detail_blurb": "The service focuses on consistent, high-protein meals designed to reduce decision fatigue.",
	},
	{
		"slug": "restore-wellness-center",
		"name": "Restore Wellness Center",
		"category": "Wellness Service",
		"category_key": "wellness-services",
		"description": "A wellness studio offering nutrition coaching, sleep support, and mindfulness sessions tailored to lifestyle goals.",
		"location": "3.6 mi away • Harbor District",
		"distance": "3.6 mi",
		"rating": 4.6,
		"match_score": 89,
		"recommendation_reason": "Recommended because its coaching options pair well with your wellness and recovery focus.",
		"promotion": "Free nutrition coaching consult with a membership plan",
		"is_featured": False,
		"is_nearby": False,
		"tags": ["wellness-services", "discounts"],
		"offers": [
			{"name": "Nutrition Coaching Consultation", "service_type": "Virtual coaching", "duration": "30 min", "difficulty": "All levels"},
			{"name": "Sleep Reset Session", "service_type": "Guided relaxation", "duration": "20 min", "difficulty": "Beginner"},
		],
		"services": [],
		"detail_blurb": "The center offers practical coaching support for sustainable habit building without medical claims.",
	},
	{
		"slug": "green-juice-bar",
		"name": "Green Juice Bar",
		"category": "Smoothie Bar",
		"category_key": "smoothie-bars",
		"description": "A fast, fresh option for smoothies, protein shakes, and simple post-workout refuels.",
		"location": "0.9 mi away • East Market",
		"distance": "0.9 mi",
		"rating": 4.5,
		"match_score": 87,
		"recommendation_reason": "Recommended because its post-workout options fit your recent active lifestyle.",
		"promotion": "Buy one, get one smoothie",
		"is_featured": False,
		"is_nearby": True,
		"tags": ["smoothie-bars", "nearby", "discounts"],
		"offers": [
			{"name": "Berry Protein Smoothie", "calories": "320 kcal", "protein": "22g", "carbs": "35g", "fat": "8g"},
		],
		"services": [],
		"detail_blurb": "This partner is useful for quick recovery drinks around workouts and commutes.",
	},
]

REWARDS_DATA = [
	{"partner": "Fresh Bowl Kitchen", "title": "20% off a high-protein meal", "description": "Enjoy a discounted protein-forward bowl for your next lunch break.", "expires": "Aug 15, 2026"},
	{"partner": "Core Strength Studio", "title": "Free seven-day gym trial", "description": "Try a guided strength program with no commitment for the first week.", "expires": "Aug 30, 2026"},
	{"partner": "Green Juice Bar", "title": "Buy one, get one smoothie", "description": "Use this reward for a post-workout refresh with a friend.", "expires": "Sep 02, 2026"},
]

OFFERS_DATA = [
	{"name": "Grilled Chicken Power Bowl", "calories": "610 kcal", "protein": "42g", "carbs": "58g", "fat": "18g"},
	{"name": "Plant-Based Protein Smoothie", "calories": "340 kcal", "protein": "24g", "carbs": "41g", "fat": "10g"},
	{"name": "Beginner Strength Training Session", "service_type": "Coach-led circuit", "duration": "45 min", "difficulty": "Beginner"},
	{"name": "Nutrition Coaching Consultation", "service_type": "Virtual coaching", "duration": "30 min", "difficulty": "All levels"},
]

NEARBY_DATA = [
	{"name": "Fresh Bowl Kitchen", "distance": "2.4 mi", "category": "Restaurant"},
	{"name": "Green Juice Bar", "distance": "0.9 mi", "category": "Smoothie Bar"},
	{"name": "Balance Meal Prep", "distance": "1.8 mi", "category": "Meal Prep"},
]


def home(request):
	if request.user.is_authenticated:
		return redirect("employee_dashboard" if request.user.is_superuser or request.user.role in User.Roles.employee_roles() else "customer_dashboard")

	customer_form = CustomerLoginForm(prefix="customer")
	employee_form = EmployeeLoginForm(prefix="employee", initial={"role": User.Roles.EMPLOYEE})

	if request.method == "POST":
		prefix = "employee" if "employee-email" in request.POST else "customer"
		form = EmployeeLoginForm(request.POST, prefix=prefix) if prefix == "employee" else CustomerLoginForm(request.POST, prefix=prefix)
		customer_form = form if prefix == "customer" else customer_form
		employee_form = form if prefix == "employee" else employee_form

		if form.is_valid():
			email = form.cleaned_data["email"]
			password = form.cleaned_data["password"]
			user = authenticate(request, username=email, password=password)

			if user and (user.role == form.cleaned_data["role"] or (user.is_superuser and form.cleaned_data["role"] == User.Roles.HR)):
				login(request, user)
				return redirect("employee_dashboard" if user.is_superuser or user.role in User.Roles.employee_roles() else "customer_dashboard")

			messages.error(request, "Invalid login details.")

	return render(
		request,
		"core/home.html",
		{
			"customer_form": customer_form,
			"employee_form": employee_form,
			"active_page": "home",
		},
	)


def account_view(request):
	if request.user.is_authenticated:
		form = ProfileForm(request.POST or None, instance=request.user)
		if request.method == "POST" and form.is_valid():
			user = form.save(commit=False)
			user.username = user.email
			user.save()
			messages.success(request, "Profile updated.")
			return redirect("account")

		return render(
			request,
			"core/profile.html",
			{
				"form": form,
				"active_page": "account",
			},
		)

	customer_form = CustomerRegistrationForm(prefix="customer")
	employee_form = EmployeeRegistrationForm(prefix="employee")

	if request.method == "POST":
		registration_form = request.POST.get("registration_form")
		if registration_form in User.Roles.employee_roles() or (registration_form is None and "employee-account_type" in request.POST):
			form = EmployeeRegistrationForm(request.POST, prefix="employee")
			employee_form = form
		else:
			form = CustomerRegistrationForm(request.POST, prefix="customer")
			customer_form = form

		if form.is_valid():
			role = form.cleaned_data["account_type"]
			email = form.cleaned_data["email"]
			password = form.cleaned_data["password"]
			user = User.objects.create_user(
				username=email,
				email=email,
				first_name=form.cleaned_data["first_name"],
				last_name=form.cleaned_data["last_name"],
				date_of_birth=form.cleaned_data.get("date_of_birth"),
				password=password,
				role=role,
			)

			user.is_staff = role in User.Roles.employee_roles()
			user.is_superuser = role == User.Roles.HR
			user.save(update_fields=["is_staff", "is_superuser"])

			if role == User.Roles.CUSTOMER:
				HealthProfile.objects.get_or_create(
					user=user,
					defaults={
						"daily_recommendation": "Log meals, water, and a short walk to build a steady routine.",
						"wellness_focus": "Consistency over intensity",
						"steps": 0,
						"water_oz": 0,
						"sleep_hours": 0,
						"workouts_per_week": 0,
					},
				)

			login(request, user)
			messages.success(request, f"{dict(User.Roles.choices).get(role, role.title())} account created.")
			return redirect("employee_dashboard" if role in User.Roles.employee_roles() else "customer_dashboard")

	return render(
		request,
		"core/account.html",
		{
			"customer_form": customer_form,
			"employee_form": employee_form,
			"active_page": "account",
		},
	)


def logout_view(request):
	logout(request)
	return redirect("home")


def employee_required(view_func):
	@wraps(view_func)
	@login_required
	def wrapped(request, *args, **kwargs):
		if not (request.user.is_superuser or request.user.role in User.Roles.employee_roles()):
			return HttpResponseForbidden("Employee access required")
		return view_func(request, *args, **kwargs)

	return wrapped


def customer_required(view_func):
	@wraps(view_func)
	@login_required
	def wrapped(request, *args, **kwargs):
		if request.user.is_superuser:
			return view_func(request, *args, **kwargs)
		if request.user.role != User.Roles.CUSTOMER:
			return redirect("employee_dashboard")
		return view_func(request, *args, **kwargs)

	return wrapped


def hr_required(view_func):
	@wraps(view_func)
	@login_required
	def wrapped(request, *args, **kwargs):
		if not request.user.is_superuser:
			return HttpResponseForbidden("HR access required")
		return view_func(request, *args, **kwargs)

	return wrapped


@hr_required
def account_management_view(request):
	accounts = User.objects.all().order_by("role", "first_name", "username")
	return render(
		request,
		"core/account_management.html",
		{
			"accounts": accounts,
			"active_page": "account_management",
		},
	)


@hr_required
@require_http_methods(["GET", "POST"])
def account_edit_view(request, pk):
	target = get_object_or_404(User, pk=pk)
	form = AccountManagementForm(request.POST or None, instance=target)

	if request.method == "POST" and form.is_valid():
		user = form.save(commit=False)
		user.username = user.email
		user.is_staff = user.role in User.Roles.employee_roles()
		user.is_superuser = user.role == User.Roles.HR
		user.save()
		messages.success(request, "Account updated.")
		return redirect("account_management")

	return render(
		request,
		"core/account_edit.html",
		{
			"form": form,
			"target": target,
			"active_page": "account_management",
		},
	)


@hr_required
@require_http_methods(["POST"])
def account_delete_view(request, pk):
	target = get_object_or_404(User, pk=pk)

	if target.pk == request.user.pk:
		messages.error(request, "You cannot delete your own account.")
		return redirect("account_management")

	target.delete()
	messages.success(request, "Account deleted.")
	return redirect("account_management")


@customer_required
def wellness_partners_view(request):
	selected_category = request.GET.get("category", "all")
	partners = [dict(partner) for partner in PARTNER_DATA if selected_category == "all" or selected_category in partner["tags"] or (selected_category == "nearby" and partner["is_nearby"]) or (selected_category == "discounts" and partner["promotion"])]
	analytics = customer_analytics(request.user)
	ai_guidance = build_ai_guidance(request.user, analytics=analytics, recommendations=relevant_recommendations(request.user), partners=partners, purpose="partners")
	partner_match_lookup = {item.get("slug"): item.get("reason") for item in ai_guidance.get("partner_matches", []) if isinstance(item, dict)}
	for partner in partners:
		partner["ai_reason"] = partner_match_lookup.get(partner["slug"], partner["recommendation_reason"])
	return render(
		request,
		"core/wellness_partners.html",
		{
			"partners": partners,
			"rewards": REWARDS_DATA,
			"offers": OFFERS_DATA,
			"nearby_partners": NEARBY_DATA,
			"ai_guidance": ai_guidance,
			"selected_category": selected_category,
			"active_page": "wellness_partners",
		},
	)


@customer_required
def wellness_partner_detail_view(request, slug):
	partner_source = next((entry for entry in PARTNER_DATA if entry["slug"] == slug), None)
	partner = dict(partner_source) if partner_source is not None else None
	if partner is None:
		raise Http404("Partner not found")
	ai_guidance = build_ai_guidance(request.user, analytics=customer_analytics(request.user), recommendations=relevant_recommendations(request.user), partners=[partner], purpose="partner_detail")
	partner["ai_reason"] = ai_guidance.get("partner_matches", [{}])[0].get("reason", partner["recommendation_reason"]) if ai_guidance.get("partner_matches") else partner["recommendation_reason"]
	return render(
		request,
		"core/wellness_partner_detail.html",
		{
			"partner": partner,
			"ai_guidance": ai_guidance,
			"active_page": "wellness_partners",
		},
	)


@customer_required
def customer_dashboard(request):
	analytics = customer_analytics(request.user)
	recommendations = relevant_recommendations(request.user)
	ai_guidance = build_ai_guidance(request.user, analytics=analytics, recommendations=recommendations, purpose="dashboard")
	return render(
		request,
		"core/customer_dashboard.html",
		{
			"analytics": analytics,
			"recommendations": recommendations,
			"ai_guidance": ai_guidance,
			"active_page": "customer",
		},
	)


@customer_required
def customer_summary_api(request):
	return JsonResponse(customer_summary_payload(request.user))


@employee_required
def employee_dashboard(request):
	form = RecommendationForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		recommendation = form.save(commit=False)
		recommendation.created_by = request.user
		recommendation.save()
		messages.success(request, "Recommendation saved.")
		return redirect("employee_dashboard")

	customers = User.objects.filter(role=User.Roles.CUSTOMER).order_by("first_name", "username")
	customer_cards = [{"user": customer, "analytics": customer_analytics(customer)} for customer in customers]

	return render(
		request,
		"core/employee_dashboard.html",
		{
			"form": form,
			"recommendations": Recommendation.objects.select_related("created_by").all()[:8],
			"customer_cards": customer_cards,
			"active_page": "employee",
		},
	)


@customer_required
@require_http_methods(["GET", "POST"])
def chat_view(request):
	chatbot_form = ChatForm(prefix="chatbot", initial={"channel": ChatMessage.Channels.CHATBOT})
	coach_form = ChatForm(prefix="coach", initial={"channel": ChatMessage.Channels.COACH})

	if request.method == "POST":
		channel = request.POST.get("channel")
		prefix = "coach" if channel == ChatMessage.Channels.COACH else "chatbot"
		form = ChatForm(request.POST, prefix=prefix)
		chatbot_form = form if prefix == "chatbot" else chatbot_form
		coach_form = form if prefix == "coach" else coach_form

		if form.is_valid():
			channel = form.cleaned_data["channel"]
			message = form.cleaned_data["message"]
			ChatMessage.objects.create(user=request.user, channel=channel, author_name="You", message=message)
			ChatMessage.objects.create(
				user=request.user,
				channel=channel,
				author_name="Coach Mira" if channel == ChatMessage.Channels.COACH else "Moderation Bot",
				message=build_chat_response(request.user, channel, message),
				is_machine_generated=True,
			)
			return redirect("chat")

	return render(
		request,
		"core/chat.html",
		{
			"chatbot_form": chatbot_form,
			"coach_form": coach_form,
			"chatbot_messages": request.user.chat_messages.filter(channel=ChatMessage.Channels.CHATBOT),
			"coach_messages": request.user.chat_messages.filter(channel=ChatMessage.Channels.COACH),
			"active_page": "chat",
		},
	)


@customer_required
@require_http_methods(["GET", "POST"])
def health_view(request):
	profile = request.user.health_profile
	form = HealthProfileForm(instance=profile)
	workout_form = WorkoutForm()
	if request.method == "POST":
		form = HealthProfileForm(request.POST, instance=profile)
		goals_text = request.POST.get("goals", "")
		if form.is_valid():
			form.save()
			request.user.health_goals.all().delete()
			goals = [line.strip() for line in goals_text.splitlines() if line.strip()]
			for index, title in enumerate(goals):
				HealthGoal.objects.create(user=request.user, title=title, sort_order=index)
			messages.success(request, "Health plan updated.")
			return redirect("health")

	analytics = customer_analytics(request.user)
	ai_guidance = build_ai_guidance(request.user, analytics=analytics, recommendations=relevant_recommendations(request.user), purpose="health")
	start_of_week = timezone.localdate() - timezone.timedelta(days=timezone.localdate().weekday())
	end_of_week = start_of_week + timezone.timedelta(days=6)
	weekly_workouts = request.user.workouts.filter(workout_date__range=[start_of_week, end_of_week]).order_by("-workout_date", "-created_at")
	weekly_minutes = sum(workout.duration_minutes for workout in weekly_workouts)
	workout_type_counts = {}
	for workout in weekly_workouts:
		workout_type_counts[workout.workout_type] = workout_type_counts.get(workout.workout_type, 0) + 1
	most_common_workout_type = None
	if workout_type_counts:
		most_common_workout_type = max(workout_type_counts.items(), key=lambda item: (item[1], item[0]))[0]
	weekly_goal = profile.workouts_per_week if profile.workouts_per_week > 0 else None
	return render(
		request,
		"core/health.html",
		{
			"form": form,
			"workout_form": workout_form,
			"goals_text": "\n".join(request.user.health_goals.values_list("title", flat=True)),
			"analytics": analytics,
			"recommendations": relevant_recommendations(request.user),
			"ai_guidance": ai_guidance,
			"recent_workouts": request.user.workouts.all()[:10],
			"weekly_workouts": weekly_workouts,
			"weekly_workout_count": weekly_workouts.count(),
			"weekly_active_minutes": weekly_minutes,
			"most_common_workout_type": most_common_workout_type,
			"weekly_goal": weekly_goal,
			"active_page": "health",
		},
	)


@customer_required
@require_http_methods(["POST"])
def workout_create_view(request):
	profile = request.user.health_profile
	form = HealthProfileForm(instance=profile)
	workout_form = WorkoutForm(request.POST)
	if workout_form.is_valid():
		workout = workout_form.save(commit=False)
		workout.user = request.user
		workout.save()
		messages.success(request, "Workout logged successfully.")
		return redirect("health")

	analytics = customer_analytics(request.user)
	ai_guidance = build_ai_guidance(request.user, analytics=analytics, recommendations=relevant_recommendations(request.user), purpose="health")
	start_of_week = timezone.localdate() - timezone.timedelta(days=timezone.localdate().weekday())
	end_of_week = start_of_week + timezone.timedelta(days=6)
	weekly_workouts = request.user.workouts.filter(workout_date__range=[start_of_week, end_of_week]).order_by("-workout_date", "-created_at")
	weekly_minutes = sum(workout.duration_minutes for workout in weekly_workouts)
	workout_type_counts = {}
	for workout in weekly_workouts:
		workout_type_counts[workout.workout_type] = workout_type_counts.get(workout.workout_type, 0) + 1
	most_common_workout_type = None
	if workout_type_counts:
		most_common_workout_type = max(workout_type_counts.items(), key=lambda item: (item[1], item[0]))[0]
	weekly_goal = profile.workouts_per_week if profile.workouts_per_week > 0 else None
	return render(
		request,
		"core/health.html",
		{
			"form": form,
			"workout_form": workout_form,
			"goals_text": "\n".join(request.user.health_goals.values_list("title", flat=True)),
			"analytics": analytics,
			"recommendations": relevant_recommendations(request.user),
			"ai_guidance": ai_guidance,
			"recent_workouts": request.user.workouts.all()[:10],
			"weekly_workouts": weekly_workouts,
			"weekly_workout_count": weekly_workouts.count(),
			"weekly_active_minutes": weekly_minutes,
			"most_common_workout_type": most_common_workout_type,
			"weekly_goal": weekly_goal,
			"active_page": "health",
		},
	)


@customer_required
@require_http_methods(["POST"])
def workout_delete_view(request, pk):
	try:
		workout = Workout.objects.get(pk=pk, user=request.user)
	except Workout.DoesNotExist:
		raise Http404("Workout not found.")
	workout.delete()
	messages.success(request, "Workout deleted.")
	return redirect("health")


@customer_required
@require_http_methods(["GET", "POST"])
def meals_view(request):
	form = MealEntryForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		meal = form.save(commit=False)
		meal.user = request.user
		meal.save()
		messages.success(request, "Meal logged.")
		return redirect("meals")

	analytics = customer_analytics(request.user)
	ai_guidance = build_ai_guidance(request.user, analytics=analytics, recommendations=relevant_recommendations(request.user), meals=list(request.user.meal_entries.all()[:5]), purpose="meals")
	return render(
		request,
		"core/meals.html",
		{
			"form": form,
			"meals": request.user.meal_entries.all()[:12],
			"analytics": analytics,
			"ai_guidance": ai_guidance,
			"active_page": "meals",
		},
	)
