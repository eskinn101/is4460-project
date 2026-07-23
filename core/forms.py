from django import forms
from django.utils import timezone

from .models import ChatMessage, HealthProfile, MealEntry, Recommendation, User, Workout


class LoginForm(forms.Form):
    role = forms.CharField(widget=forms.HiddenInput())
    email = forms.CharField(label="Email")
    password = forms.CharField(widget=forms.PasswordInput())
    fixed_role = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.fixed_role:
            self.fields["role"].initial = self.fixed_role

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")

        if self.fixed_role and role and role != self.fixed_role:
            self.add_error("role", "Invalid role for this form.")

        return cleaned_data


class CustomerLoginForm(LoginForm):
	fixed_role = User.Roles.CUSTOMER


class EmployeeLoginForm(LoginForm):
	role = forms.ChoiceField(choices=User.Roles.employee_choices())


class AccountRegistrationForm(forms.Form):
    account_type = forms.ChoiceField(choices=User.Roles.choices, widget=forms.HiddenInput())
    first_name = forms.CharField(max_length=120)
    last_name = forms.CharField(max_length=120)
    email = forms.EmailField()
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    password = forms.CharField(widget=forms.PasswordInput())
    confirm_password = forms.CharField(widget=forms.PasswordInput())
    fixed_account_type = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.fixed_account_type:
            self.fields["account_type"].initial = self.fixed_account_type

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with that email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        account_type = cleaned_data.get("account_type")
        date_of_birth = cleaned_data.get("date_of_birth")
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if account_type in User.Roles.employee_roles() and not date_of_birth:
            self.add_error("date_of_birth", "Birthday is required for employee accounts.")

        if self.fixed_account_type and account_type and account_type != self.fixed_account_type:
            self.add_error("account_type", "Invalid account type for this form.")

        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")

        return cleaned_data


class CustomerRegistrationForm(AccountRegistrationForm):
    fixed_account_type = User.Roles.CUSTOMER


class EmployeeRegistrationForm(AccountRegistrationForm):
    account_type = forms.ChoiceField(choices=User.Roles.employee_choices())


class AccountManagementForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "role"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("An account with that email already exists.")
        return email


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["email", "phone_number", "date_of_birth", "city", "state"]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "phone_number": forms.TextInput(attrs={"placeholder": "(555) 555-5555"}),
            "city": forms.TextInput(attrs={"placeholder": "City"}),
            "state": forms.TextInput(attrs={"placeholder": "State"}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("An account with that email already exists.")
        return email


class RecommendationForm(forms.ModelForm):
    class Meta:
        model = Recommendation
        fields = ["title", "category", "guidance", "analytics_focus"]
        widgets = {
            "guidance": forms.Textarea(attrs={"rows": 4}),
            "analytics_focus": forms.TextInput(attrs={"placeholder": "Hydration, recovery, meal consistency..."}),
        }


class RecommendationImportForm(forms.Form):
    file = forms.FileField(help_text="Upload a CSV file, or a ZIP that contains one CSV file, with title, category, guidance, and optional analytics_focus columns.")
    replace_existing = forms.BooleanField(
        required=False,
        initial=False,
        help_text="Replace all current recommendations before importing.",
    )

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]
        file_name = uploaded_file.name.lower()
        if not (file_name.endswith(".csv") or file_name.endswith(".zip")):
            raise forms.ValidationError("Please upload a CSV file or a ZIP file that contains a CSV.")
        return uploaded_file


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(item, initial) for item in data]
        return [single_file_clean(data, initial)]


class RecommendationMultiImportForm(forms.Form):
    files = MultipleFileField(
        widget=MultipleFileInput(attrs={"multiple": True}),
        help_text="Select one or multiple CSV/ZIP files.",
    )
    replace_existing = forms.BooleanField(
        required=False,
        initial=False,
        help_text="Replace current recommendation library before importing the first file.",
    )

    def clean_files(self):
        uploaded_files = self.cleaned_data["files"]
        if not uploaded_files:
            raise forms.ValidationError("Select at least one file to upload.")

        for uploaded_file in uploaded_files:
            file_name = uploaded_file.name.lower()
            if not (file_name.endswith(".csv") or file_name.endswith(".zip")):
                raise forms.ValidationError("All files must be CSV or ZIP.")

        return uploaded_files


class ChatForm(forms.Form):
    channel = forms.ChoiceField(choices=ChatMessage.Channels.choices, widget=forms.HiddenInput())
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}))


class HealthProfileForm(forms.ModelForm):
    class Meta:
        model = HealthProfile
        fields = ["daily_recommendation", "wellness_focus", "steps", "water_oz", "sleep_hours", "workouts_per_week"]
        widgets = {
            "daily_recommendation": forms.Textarea(attrs={"rows": 4}),
        }


class MealEntryForm(forms.ModelForm):
    class Meta:
        model = MealEntry
        fields = ["meal_name", "time_of_day", "calories", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 4}),
        }


class WorkoutForm(forms.ModelForm):
    class Meta:
        model = Workout
        fields = ["workout_type", "workout_date", "duration_minutes", "intensity", "notes"]
        widgets = {
            "workout_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.data and not self.is_bound:
            self.fields["workout_date"].initial = timezone.localdate()

    def clean_duration_minutes(self):
        duration_minutes = self.cleaned_data.get("duration_minutes")
        if duration_minutes is not None and duration_minutes <= 0:
            raise forms.ValidationError("Duration must be greater than 0.")
        return duration_minutes