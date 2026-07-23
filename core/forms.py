from django import forms

from .models import ChatMessage, HealthProfile, MealEntry, Recommendation, User


class LoginForm(forms.Form):
    role = forms.CharField(widget=forms.HiddenInput())
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput())


class AccountRegistrationForm(forms.Form):
    account_type = forms.ChoiceField(choices=User.Roles.choices)
    first_name = forms.CharField(max_length=120)
    last_name = forms.CharField(max_length=120)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput())
    confirm_password = forms.CharField(widget=forms.PasswordInput())

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with that email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")

        return cleaned_data


class RecommendationForm(forms.ModelForm):
    class Meta:
        model = Recommendation
        fields = ["title", "category", "guidance", "analytics_focus"]
        widgets = {
            "guidance": forms.Textarea(attrs={"rows": 4}),
            "analytics_focus": forms.TextInput(attrs={"placeholder": "Hydration, recovery, meal consistency..."}),
        }


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