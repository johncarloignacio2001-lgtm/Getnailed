from django.urls import path

from . import views


app_name = "services"
urlpatterns = [
    path("", views.index, name="index"),
    path("new/", views.service_create, name="service_create"),
    path("<int:pk>/edit/", views.service_update, name="service_update"),
    path("<int:pk>/delete/", views.service_delete, name="service_delete"),
    path("categories/", views.category_list, name="category_list"),
    path("categories/new/", views.category_create, name="category_create"),
    path("categories/<int:pk>/edit/", views.category_update, name="category_update"),
    path("categories/<int:pk>/delete/", views.category_delete, name="category_delete"),
    path("staff/", views.staff_list, name="staff_list"),
    path("staff/new/", views.staff_create, name="staff_create"),
    path("staff/<int:pk>/edit/", views.staff_update, name="staff_update"),
    path("staff/<int:pk>/delete/", views.staff_delete, name="staff_delete"),
]
