from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import ChatMessage, HealthGoal, HealthProfile, MealEntry, Recommendation, RecommendationDataFile, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
	fieldsets = DjangoUserAdmin.fieldsets + (("Moderation", {"fields": ("role",)}),)
	list_display = ("username", "email", "role", "is_staff")


admin.site.register(HealthProfile)
admin.site.register(HealthGoal)
admin.site.register(MealEntry)
admin.site.register(Recommendation)
admin.site.register(RecommendationDataFile)
admin.site.register(ChatMessage)
