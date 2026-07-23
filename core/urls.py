from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("logout/", views.logout_view, name="logout"),
    path("customer/", views.customer_dashboard, name="customer_dashboard"),
    path("api/customer/summary/", views.customer_summary_api, name="customer_summary_api"),
    path("employee/", views.employee_dashboard, name="employee_dashboard"),
    path("chat/", views.chat_view, name="chat"),
    path("health/", views.health_view, name="health"),
    path("meals/", views.meals_view, name="meals"),
]