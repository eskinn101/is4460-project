from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import AccountRegistrationForm, ChatForm, HealthProfileForm, LoginForm, MealEntryForm, ProfileForm, RecommendationForm
from .models import ChatMessage, HealthGoal, HealthProfile, Recommendation, User
from .services import build_chat_response, customer_analytics, customer_summary_payload, relevant_recommendations


def home(request):
	if request.user.is_authenticated:
		return redirect("employee_dashboard" if request.user.role == User.Roles.EMPLOYEE else "customer_dashboard")

	customer_form = LoginForm(prefix="customer", initial={"role": User.Roles.CUSTOMER})
	employee_form = LoginForm(prefix="employee", initial={"role": User.Roles.EMPLOYEE})

	if request.method == "POST":
		prefix = "employee" if "employee-email" in request.POST else "customer"
		form = LoginForm(request.POST, prefix=prefix)
		customer_form = form if prefix == "customer" else customer_form
		employee_form = form if prefix == "employee" else employee_form

		if form.is_valid():
			email = form.cleaned_data["email"]
			password = form.cleaned_data["password"]
			user = authenticate(request, username=email, password=password)

			if user and user.role == form.cleaned_data["role"]:
				login(request, user)
				return redirect("employee_dashboard" if user.role == User.Roles.EMPLOYEE else "customer_dashboard")

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

	form = AccountRegistrationForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		role = form.cleaned_data["account_type"]
		email = form.cleaned_data["email"]
		password = form.cleaned_data["password"]
		user = User.objects.create_user(
			username=email,
			email=email,
			first_name=form.cleaned_data["first_name"],
			last_name=form.cleaned_data["last_name"],
			password=password,
			role=role,
		)

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
		messages.success(request, f"{role.title()} account created.")
		return redirect("employee_dashboard" if role == User.Roles.EMPLOYEE else "customer_dashboard")

	return render(
		request,
		"core/account.html",
		{
			"form": form,
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
		if request.user.role != User.Roles.EMPLOYEE:
			return HttpResponseForbidden("Employee access required")
		return view_func(request, *args, **kwargs)

	return wrapped


def customer_required(view_func):
	@wraps(view_func)
	@login_required
	def wrapped(request, *args, **kwargs):
		if request.user.role != User.Roles.CUSTOMER:
			return redirect("employee_dashboard")
		return view_func(request, *args, **kwargs)

	return wrapped


@customer_required
def customer_dashboard(request):
	analytics = customer_analytics(request.user)
	recommendations = relevant_recommendations(request.user)
	return render(
		request,
		"core/customer_dashboard.html",
		{
			"analytics": analytics,
			"recommendations": recommendations,
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
	else:
		form = HealthProfileForm(instance=profile)

	analytics = customer_analytics(request.user)
	return render(
		request,
		"core/health.html",
		{
			"form": form,
			"goals_text": "\n".join(request.user.health_goals.values_list("title", flat=True)),
			"analytics": analytics,
			"recommendations": relevant_recommendations(request.user),
			"active_page": "health",
		},
	)


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
	return render(
		request,
		"core/meals.html",
		{
			"form": form,
			"meals": request.user.meal_entries.all()[:12],
			"analytics": analytics,
			"active_page": "meals",
		},
	)
