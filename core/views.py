import os
import csv
import io
import zipfile
from functools import wraps
from urllib.request import urlopen

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.http import require_http_methods

from .forms import (
	AccountManagementForm,
	AccountRegistrationForm,
	BotBehaviorConfigForm,
	ChatForm,
	CustomerBotBehaviorOverrideForm,
	CustomerRegistrationForm,
	CustomerLoginForm,
	EmployeeRegistrationForm,
	EmployeeLoginForm,
	HealthProfileForm,
	LoginForm,
	MealEntryForm,
	RecommendationMultiImportForm,
	RecommendationRemoteImportForm,
	RecommendationForm,
)
from .models import BotBehaviorConfig, BotBehaviorRevision, ChatMessage, CustomerBotBehaviorOverride, HealthGoal, Recommendation, RecommendationDataFile, User
from .services import build_chat_payload, build_chat_response, customer_analytics, customer_summary_payload, goal_progress_snapshot, interpret_goal_message, relevant_recommendations


def home(request):
	if request.user.is_authenticated:
		return redirect("employee_dashboard" if request.user.role in User.Roles.employee_roles() else "customer_dashboard")

	customer_form = CustomerLoginForm(prefix="customer")
	employee_form = EmployeeLoginForm(prefix="employee")

	if request.method == "POST":
		prefix = "employee" if "employee-email" in request.POST else "customer"
		form_class = EmployeeLoginForm if prefix == "employee" else CustomerLoginForm
		form = form_class(request.POST, prefix=prefix)
		customer_form = form if prefix == "customer" else customer_form
		employee_form = form if prefix == "employee" else employee_form

		if form.is_valid():
			email = form.cleaned_data["email"]
			password = form.cleaned_data["password"]
			user = authenticate(request, username=email, password=password)

			if user and user.role == form.cleaned_data["role"]:
				login(request, user)
				return redirect("employee_dashboard" if user.role in User.Roles.employee_roles() else "customer_dashboard")

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


def logout_view(request):
	logout(request)
	return redirect("home")


def employee_required(view_func):
	@wraps(view_func)
	@login_required
	def wrapped(request, *args, **kwargs):
		if request.user.role not in User.Roles.employee_roles():
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
	ai_guidance = {
		"summary": f"Current score is {analytics['consistency_score']} with {analytics['goal_count']} active goals.",
		"meal_tip": "Anchor meals with protein and hydration to improve recovery and fat-loss consistency.",
		"partner_tip": "Use Chat for targeted recommendations and Goals to track progress each week.",
	}
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
def goals_view(request):
	snapshot = goal_progress_snapshot(request.user)
	return render(
		request,
		"core/goals.html",
		{
			"goal_snapshot": snapshot,
			"active_page": "goals",
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
	latest_chat_sources = request.session.get("latest_chat_sources")

	if request.method == "POST":
		channel = request.POST.get("channel")
		prefix = "coach" if channel == ChatMessage.Channels.COACH else "chatbot"
		form = ChatForm(request.POST, prefix=prefix)
		chatbot_form = form if prefix == "chatbot" else chatbot_form
		coach_form = form if prefix == "coach" else coach_form

		if form.is_valid():
			channel = form.cleaned_data["channel"]
			message = form.cleaned_data["message"]
			goal_result = interpret_goal_message(request.user, message, commit=True)
			ChatMessage.objects.create(user=request.user, channel=channel, author_name="You", message=message)
			chat_payload = build_chat_payload(request.user, channel, message)
			bot_message = chat_payload["reply"]
			if goal_result:
				bot_message = f"{bot_message} {goal_result['message']} You can review it on your Health page."
				chat_payload["sources"]["goals"] = [goal_result["message"]]
			ChatMessage.objects.create(
				user=request.user,
				channel=channel,
				author_name="Coach Mira" if channel == ChatMessage.Channels.COACH else "Moderation Bot",
				message=bot_message,
				is_machine_generated=True,
			)
			request.session["latest_chat_sources"] = {
				"channel": channel,
				"message": message,
				"sources": chat_payload["sources"],
			}
			return redirect("chat")

	return render(
		request,
		"core/chat.html",
		{
			"chatbot_form": chatbot_form,
			"coach_form": coach_form,
			"chatbot_messages": request.user.chat_messages.filter(channel=ChatMessage.Channels.CHATBOT),
			"coach_messages": request.user.chat_messages.filter(channel=ChatMessage.Channels.COACH),
			"latest_chat_sources": latest_chat_sources,
			"active_page": "chat",
		},
	)


@customer_required
@require_http_methods(["GET", "POST"])
def health_view(request):
	profile = request.user.health_profile
	goals_queryset = request.user.health_goals.order_by("sort_order", "id")
	selected_goal_id = request.GET.get("edit_goal")
	selected_goal = goals_queryset.filter(pk=selected_goal_id).first() if selected_goal_id else None
	if request.method == "POST":
		action = request.POST.get("action", "save_profile")
		form = HealthProfileForm(request.POST, instance=profile)
		if action == "save_profile":
			if form.is_valid():
				form.save()
				messages.success(request, "Health plan updated.")
				return redirect("health")
		elif action == "add_goal":
			new_goal_title = (request.POST.get("new_goal_title") or "").strip()
			if new_goal_title:
				sort_order = goals_queryset.count()
				HealthGoal.objects.create(user=request.user, title=new_goal_title[:255], sort_order=sort_order)
				messages.success(request, "Goal added.")
				return redirect("health")
			messages.error(request, "Enter a goal before saving.")
		elif action == "update_goal":
			goal = goals_queryset.filter(pk=request.POST.get("goal_id")).first()
			updated_title = (request.POST.get("goal_title") or "").strip()
			if goal and updated_title:
				goal.title = updated_title[:255]
				goal.save(update_fields=["title"])
				messages.success(request, "Goal updated.")
				return redirect("health")
			messages.error(request, "Unable to update that goal.")
		elif action == "delete_goal":
			goal = goals_queryset.filter(pk=request.POST.get("goal_id")).first()
			if goal:
				goal.delete()
				messages.success(request, "Goal removed.")
				return redirect("health")
			messages.error(request, "Goal not found.")
	else:
		form = HealthProfileForm(instance=profile)

	analytics = customer_analytics(request.user)
	recommendations = relevant_recommendations(request.user)
	primary_guidance = recommendations[0].guidance if recommendations else analytics["insights"][0]
	ai_guidance = {
		"health_tip": primary_guidance,
		"summary": f"You currently have {analytics['goal_count']} tracked goals. Use this page or the chatbot to create, edit, or remove goals.",
	}
	return render(
		request,
		"core/health.html",
		{
			"form": form,
			"goals": goals_queryset,
			"selected_goal": selected_goal,
			"analytics": analytics,
			"recommendations": recommendations,
			"ai_guidance": ai_guidance,
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


def account_view(request):
	"""Registration page for both customers and employees."""
	customer_form = CustomerRegistrationForm(prefix="customer")
	employee_form = EmployeeRegistrationForm(prefix="employee")

	if request.method == "POST":
		prefix = "employee" if "employee-email" in request.POST else "customer"
		form_class = EmployeeRegistrationForm if prefix == "employee" else CustomerRegistrationForm
		form = form_class(request.POST, prefix=prefix)
		customer_form = form if prefix == "customer" else customer_form
		employee_form = form if prefix == "employee" else employee_form

		if form.is_valid():
			user = User.objects.create_user(
				email=form.cleaned_data["email"],
				username=form.cleaned_data["email"],
				first_name=form.cleaned_data["first_name"],
				last_name=form.cleaned_data["last_name"],
				password=form.cleaned_data["password"],
				role=form.cleaned_data["account_type"],
				date_of_birth=form.cleaned_data.get("date_of_birth"),
			)
			messages.success(request, f"Account created! Please log in.")
			return redirect("home")

	return render(
		request,
		"core/account.html",
		{
			"customer_form": customer_form,
			"employee_form": employee_form,
			"active_page": "account",
		},
	)


def _wellness_partners_catalog():
	"""Static partner data used for prototype wellness partner pages."""
	return [
		{
			"slug": "fit-bowl-cafe",
			"name": "Fit Bowl Cafe",
			"category": "restaurants",
			"description": "Balanced bowls with macro-friendly add-ons and high-protein options.",
			"location": "Downtown",
			"rating": "4.7",
			"match_score": 92,
			"ai_reason": "Matches your protein-forward nutrition goals.",
			"detail_blurb": "Strong fit for post-workout meals and stable daily calorie targets.",
			"promotion": "10% off first order",
			"offers": [
				{"name": "Chicken Power Bowl", "calories": 520, "protein": 42, "carbs": 44, "fat": 16},
				{"name": "Salmon Grain Plate", "calories": 610, "protein": 38, "carbs": 50, "fat": 24},
			],
		},
		{
			"slug": "stride-lab-gym",
			"name": "Stride Lab Gym",
			"category": "gyms",
			"description": "Technique-focused coaching with beginner to intermediate training plans.",
			"location": "Midtown",
			"rating": "4.8",
			"match_score": 88,
			"ai_reason": "Supports your consistency and weekly workout goals.",
			"detail_blurb": "Great option to build a repeatable weekly training routine.",
			"promotion": "Free first class",
			"offers": [
				{"name": "Strength Foundations", "service_type": "Class", "duration": "45 min", "difficulty": "Beginner"},
				{"name": "Conditioning Circuit", "service_type": "Class", "duration": "50 min", "difficulty": "Moderate"},
			],
		},
	]


def _map_recommendation_category(raw_value):
	value = (raw_value or "").strip().lower()
	if value in {"diet", "nutrition", "meal", "meals"}:
		return Recommendation.Categories.DIET
	if value in {"exercise", "fitness", "workout", "training"}:
		return Recommendation.Categories.EXERCISE
	if value in {"wellness", "recovery", "sleep", "hydration", "stress"}:
		return Recommendation.Categories.WELLNESS
	if "fit" in value or "workout" in value:
		return Recommendation.Categories.EXERCISE
	if "diet" in value or "nutri" in value:
		return Recommendation.Categories.DIET
	return Recommendation.Categories.WELLNESS


def _normalize_header(header):
	return (header or "").strip().lower().replace(" ", "_")


def _recommendation_payloads_from_csv_bytes(raw_bytes):
	decoded = raw_bytes.decode("utf-8-sig", errors="ignore")
	reader = csv.DictReader(io.StringIO(decoded))
	if not reader.fieldnames:
		return []

	header_lookup = {_normalize_header(item): item for item in reader.fieldnames}
	title_key = header_lookup.get("title") or header_lookup.get("name") or header_lookup.get("recommendation")
	category_key = header_lookup.get("category") or header_lookup.get("type")
	guidance_key = header_lookup.get("guidance") or header_lookup.get("description") or header_lookup.get("recommendation")
	focus_key = header_lookup.get("analytics_focus") or header_lookup.get("focus") or header_lookup.get("tags")

	if not title_key or not guidance_key:
		return []

	payloads = []
	for row in reader:
		title = (row.get(title_key) or "").strip()
		guidance = (row.get(guidance_key) or "").strip()
		if not title or not guidance:
			continue
		payloads.append(
			{
				"title": title[:255],
				"category": _map_recommendation_category(row.get(category_key) if category_key else ""),
				"guidance": guidance,
				"analytics_focus": (row.get(focus_key) or "").strip()[:255] if focus_key else "",
			}
		)
	return payloads


def _recommendation_payloads_from_uploaded_file(uploaded_file):
	raw_bytes = uploaded_file.read()
	name = uploaded_file.name.lower()
	payloads = []

	if name.endswith(".zip"):
		with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zip_ref:
			for member in zip_ref.namelist():
				if not member.lower().endswith(".csv"):
					continue
				payloads.extend(_recommendation_payloads_from_csv_bytes(zip_ref.read(member)))
	else:
		payloads = _recommendation_payloads_from_csv_bytes(raw_bytes)

	return raw_bytes, payloads


@login_required
def wellness_partners_view(request):
	"""Display wellness partners and local recommendations."""
	category = request.GET.get("category", "all")
	all_partners = _wellness_partners_catalog()
	partners = all_partners if category == "all" else [p for p in all_partners if p["category"] == category]
	selected_category = category
	ai_guidance = {"partner_tip": "Based on your health profile, we recommend exploring high-protein options and nearby gyms."}
	rewards = [
		{"partner": "Fit Bowl Cafe", "title": "10% off first order", "description": "Use code MOD10 at checkout.", "expires": "Aug 31"},
		{"partner": "Stride Lab Gym", "title": "Free first class", "description": "Redeem one intro session.", "expires": "Sep 15"},
	]
	offers = [offer for partner in partners for offer in partner.get("offers", [])][:6]
	nearby_partners = [{"name": p["name"], "distance": "1.2 mi", "category": p["category"].replace("-", " ").title()} for p in partners[:4]]
	
	return render(
		request,
		"core/wellness_partners.html",
		{
			"partners": partners,
			"selected_category": selected_category,
			"ai_guidance": ai_guidance,
			"rewards": rewards,
			"offers": offers,
			"nearby_partners": nearby_partners,
			"active_page": "wellness_partners",
		},
	)


@login_required
def wellness_partner_detail_view(request, slug):
	"""Display details for a single wellness partner."""
	partners = _wellness_partners_catalog()
	partner = next((item for item in partners if item["slug"] == slug), None)
	if partner is None:
		messages.error(request, "Partner not found.")
		return redirect("wellness_partners")

	return render(
		request,
		"core/wellness_partner_detail.html",
		{
			"partner": partner,
			"active_page": "wellness_partners",
		},
	)


@employee_required
def recommendation_files_view(request):
	"""Employee view to manage recommendation files and behavior blending settings."""
	can_manage_files = request.user.is_superuser or request.user.role == User.Roles.HR
	general_recommendation_count = Recommendation.objects.count()
	customers = User.objects.filter(role=User.Roles.CUSTOMER).order_by("first_name", "username")
	selected_customer = None
	selected_customer_id = request.GET.get("customer") or request.POST.get("customer_id")
	if selected_customer_id:
		selected_customer = customers.filter(pk=selected_customer_id).first()
	if selected_customer is None:
		selected_customer = customers.first()

	behavior_config, _ = BotBehaviorConfig.objects.get_or_create()
	customer_override = None
	if selected_customer:
		customer_override = CustomerBotBehaviorOverride.objects.filter(user=selected_customer).first()

	import_form = RecommendationMultiImportForm()
	remote_import_form = RecommendationRemoteImportForm()
	behavior_form = BotBehaviorConfigForm(instance=behavior_config, prefix="global_behavior")
	customer_behavior_form = CustomerBotBehaviorOverrideForm(instance=customer_override, prefix="customer_behavior")
	preview_message = ""
	preview_output = None

	if request.method == "POST" and can_manage_files:
		action = request.POST.get("action")
		preview_message = request.POST.get("preview_message", "").strip()

		if action == "save_behavior_instructions":
			behavior_form = BotBehaviorConfigForm(request.POST, instance=behavior_config, prefix="global_behavior")
			if behavior_form.is_valid():
				updated = behavior_form.save(commit=False)
				updated.updated_by = request.user
				updated.save()
				BotBehaviorRevision.objects.create(
					scope=BotBehaviorRevision.Scopes.GLOBAL,
					instructions=updated.instructions,
					updated_by=request.user,
				)
				messages.success(request, "Global behavior policy saved.")
				return redirect("recommendation_files")

		elif action == "save_customer_behavior_override":
			if not selected_customer:
				messages.error(request, "Select a customer before saving an override.")
			else:
				override, _ = CustomerBotBehaviorOverride.objects.get_or_create(user=selected_customer)
				customer_behavior_form = CustomerBotBehaviorOverrideForm(request.POST, instance=override, prefix="customer_behavior")
				if customer_behavior_form.is_valid():
					updated_override = customer_behavior_form.save(commit=False)
					updated_override.updated_by = request.user
					updated_override.save()
					BotBehaviorRevision.objects.create(
						scope=BotBehaviorRevision.Scopes.CUSTOMER,
						customer=selected_customer,
						instructions=updated_override.instructions,
						updated_by=request.user,
					)
					messages.success(request, "Customer behavior override saved.")
					return redirect(f"{redirect('recommendation_files').url}?customer={selected_customer.id}")

		elif action == "preview_behavior":
			behavior_form = BotBehaviorConfigForm(request.POST, instance=behavior_config, prefix="global_behavior")
			preview_override = customer_override.instructions if customer_override else ""
			if selected_customer:
				bound_override = CustomerBotBehaviorOverrideForm(request.POST, instance=customer_override, prefix="customer_behavior")
				if bound_override.is_valid():
					customer_behavior_form = bound_override
					preview_override = bound_override.cleaned_data.get("instructions", "")
				else:
					customer_behavior_form = bound_override

			if behavior_form.is_valid():
				instructions = behavior_form.cleaned_data.get("instructions", "")
				preview_user = selected_customer or request.user
				preview_analytics = customer_analytics(preview_user)
				preview_recommendations = relevant_recommendations(preview_user)
				rec_title = preview_recommendations[0].title if preview_recommendations else "No recommendation loaded"
				health_tip = (
					"Increase hydration first today."
					if preview_analytics["water_oz"] < 64
					else "Hydration is on track; focus on sleep and activity consistency."
				)
				chat_preview_payload = build_chat_payload(
					preview_user,
					ChatMessage.Channels.CHATBOT,
					preview_message or "What should I focus on today?",
					global_instructions=instructions,
					customer_override=preview_override,
				)
				chat_preview = chat_preview_payload["reply"]
				goal_action = interpret_goal_message(preview_user, preview_message, commit=False)
				if goal_action:
					chat_preview_payload["sources"]["goals"] = [goal_action["message"]]
				preview_output = {
					"summary": (
						f"Policy words: {len(instructions.split())}. "
						f"Customer score: {preview_analytics['consistency_score']}. "
						f"Top recommendation source: {rec_title}."
					),
					"health_tip": health_tip,
					"chat_reply": chat_preview,
					"goal_action": goal_action,
					"sources": chat_preview_payload["sources"],
				}

		elif action == "restore_behavior_revision":
			revision_id = request.POST.get("revision_id")
			revision = BotBehaviorRevision.objects.filter(pk=revision_id).first()
			if not revision:
				messages.error(request, "Revision not found.")
			elif revision.scope == BotBehaviorRevision.Scopes.GLOBAL:
				behavior_config.instructions = revision.instructions
				behavior_config.updated_by = request.user
				behavior_config.save(update_fields=["instructions", "updated_by", "updated_at"])
				messages.success(request, "Global behavior revision restored.")
				return redirect("recommendation_files")
			else:
				target_customer = selected_customer or revision.customer
				if target_customer:
					override, _ = CustomerBotBehaviorOverride.objects.get_or_create(user=target_customer)
					override.instructions = revision.instructions
					override.updated_by = request.user
					override.save(update_fields=["instructions", "updated_by", "updated_at"])
					messages.success(request, "Customer behavior revision restored.")
					return redirect(f"{redirect('recommendation_files').url}?customer={target_customer.id}")

		elif action == "bulk_delete_files":
			selected_ids = request.POST.getlist("selected_files")
			for data_file in RecommendationDataFile.objects.filter(pk__in=selected_ids):
				if data_file.file:
					data_file.file.delete(save=False)
				data_file.delete()
			if selected_ids:
				messages.success(request, f"Deleted {len(selected_ids)} selected file(s).")
			return redirect("recommendation_files")

		elif action == "upload_files":
			import_form = RecommendationMultiImportForm(request.POST, request.FILES)
			if import_form.is_valid():
				uploaded = import_form.cleaned_data["files"]
				replace_existing = import_form.cleaned_data.get("replace_existing", False)
				if replace_existing:
					Recommendation.objects.all().delete()

				for uploaded_file in uploaded:
					raw_bytes, payloads = _recommendation_payloads_from_uploaded_file(uploaded_file)
					if payloads:
						Recommendation.objects.bulk_create(
							[
								Recommendation(
									title=item["title"],
									category=item["category"],
									guidance=item["guidance"],
									analytics_focus=item["analytics_focus"],
									created_by=request.user,
								)
								for item in payloads
							]
						)
					RecommendationDataFile.objects.create(
						file=ContentFile(raw_bytes, name=uploaded_file.name),
						original_name=uploaded_file.name,
						imported_rows=len(payloads),
						uploaded_by=request.user,
					)
				messages.success(request, f"Uploaded {len(uploaded)} file(s).")
				return redirect("recommendation_files")

		elif action == "import_remote_source":
			remote_import_form = RecommendationRemoteImportForm(request.POST)
			if remote_import_form.is_valid():
				source_path = remote_import_form.cleaned_data.get("source_path")
				source_url = remote_import_form.cleaned_data.get("source_url")
				replace_existing = remote_import_form.cleaned_data.get("replace_existing", False)
				if replace_existing:
					Recommendation.objects.all().delete()

				raw_bytes = b""
				label = source_path or source_url or "remote-source.csv"
				if source_path:
					with open(source_path, "rb") as handle:
						raw_bytes = handle.read()
				elif source_url:
					with urlopen(source_url, timeout=8) as response:
						raw_bytes = response.read()

				if label.lower().endswith(".zip"):
					payloads = []
					with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zip_ref:
						for member in zip_ref.namelist():
							if member.lower().endswith(".csv"):
								payloads.extend(_recommendation_payloads_from_csv_bytes(zip_ref.read(member)))
				else:
					payloads = _recommendation_payloads_from_csv_bytes(raw_bytes)

				if payloads:
					Recommendation.objects.bulk_create(
						[
							Recommendation(
								title=item["title"],
								category=item["category"],
								guidance=item["guidance"],
								analytics_focus=item["analytics_focus"],
								created_by=request.user,
							)
							for item in payloads
						]
					)
				RecommendationDataFile.objects.create(
					file=ContentFile(raw_bytes, name=os.path.basename(label) or "remote-source.csv"),
					original_name=os.path.basename(label),
					imported_rows=len(payloads),
					uploaded_by=request.user,
				)
				messages.success(request, f"Remote source imported with {len(payloads)} recommendation rows.")
				return redirect("recommendation_files")

	selected_analytics = customer_analytics(selected_customer) if selected_customer else None
	selected_recommendations = relevant_recommendations(selected_customer) if selected_customer else []
	global_revisions = BotBehaviorRevision.objects.filter(scope=BotBehaviorRevision.Scopes.GLOBAL).select_related("updated_by")[:20]
	customer_revisions = (
		BotBehaviorRevision.objects.filter(scope=BotBehaviorRevision.Scopes.CUSTOMER, customer=selected_customer).select_related("updated_by")[:20]
		if selected_customer
		else []
	)
	uploaded_files = RecommendationDataFile.objects.select_related("uploaded_by").all()[:50]

	return render(
		request,
		"core/recommendation_files.html",
		{
			"general_recommendation_count": general_recommendation_count,
			"can_manage_files": can_manage_files,
			"import_form": import_form,
			"remote_import_form": remote_import_form,
			"behavior_config": behavior_config,
			"behavior_form": behavior_form,
			"customer_behavior_form": customer_behavior_form,
			"customers": customers,
			"selected_customer": selected_customer,
			"selected_analytics": selected_analytics,
			"selected_recommendations": selected_recommendations,
			"preview_message": preview_message,
			"preview_output": preview_output,
			"global_revisions": global_revisions,
			"customer_revisions": customer_revisions,
			"uploaded_files": uploaded_files,
			"active_page": "recommendation_files",
		},
	)


def superuser_required(view_func):
	@wraps(view_func)
	@login_required
	def wrapped(request, *args, **kwargs):
		if not request.user.is_superuser:
			return HttpResponseForbidden("Admin access required")
		return view_func(request, *args, **kwargs)
	return wrapped


@superuser_required
def account_management_view(request):
	"""Superuser view to manage all accounts."""
	accounts = User.objects.all().order_by("first_name", "last_name")
	return render(
		request,
		"core/account_management.html",
		{
			"accounts": accounts,
			"active_page": "account_management",
		},
	)


@superuser_required
@require_http_methods(["GET", "POST"])
def account_edit_view(request, pk):
	"""Superuser view to edit an account."""
	account = get_object_or_404(User, pk=pk)
	form = AccountManagementForm(request.POST or None, instance=account)

	if request.method == "POST" and form.is_valid():
		form.save()
		messages.success(request, f"Account for {account.get_full_name()} updated.")
		return redirect("account_management")

	return render(
		request,
		"core/account_edit.html",
		{
			"form": form,
			"account": account,
			"active_page": "account_management",
		},
	)


@superuser_required
@require_http_methods(["POST"])
def account_delete_view(request, pk):
	"""Superuser view to delete an account."""
	account = get_object_or_404(User, pk=pk)
	if account.pk == request.user.pk:
		messages.error(request, "You cannot delete your own account.")
	else:
		account.delete()
		messages.success(request, "Account deleted.")
	return redirect("account_management")
