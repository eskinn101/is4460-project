from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("logout/", views.logout_view, name="logout"),
    path("account/", views.account_view, name="account"),
    path("customer/", views.customer_dashboard, name="customer_dashboard"),
    path("api/customer/summary/", views.customer_summary_api, name="customer_summary_api"),
    path("employee/", views.employee_dashboard, name="employee_dashboard"),
    path("chat/", views.chat_view, name="chat"),
    path("goals/", views.goals_view, name="goals"),
    path("health/", views.health_view, name="health"),
    path("meals/", views.meals_view, name="meals"),
    path("wellness-partners/", views.wellness_partners_view, name="wellness_partners"),
    path("wellness-partners/<slug:slug>/", views.wellness_partner_detail_view, name="wellness_partner_detail"),
    path("recommendation-files/", views.recommendation_files_view, name="recommendation_files"),
    path("accounts/manage/", views.account_management_view, name="account_management"),
    path("accounts/<int:pk>/edit/", views.account_edit_view, name="account_edit"),
    path("accounts/<int:pk>/delete/", views.account_delete_view, name="account_delete"),
]