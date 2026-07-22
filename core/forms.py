from django import forms

from .models import ChatMessage, HealthProfile, MealEntry, Recommendation


class LoginForm(forms.Form):
    role = forms.CharField(widget=forms.HiddenInput())
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput())


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