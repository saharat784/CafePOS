from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('menu/', views.menu, name='menu'),
    path('cart/', views.cart, name='cart'),
    path('queue/', views.customer_queue, name='customer_queue'),
    path('barista/', views.barista, name='barista'),
    path('inventory/', views.inventory, name='inventory'),
    path('export-report/', views.export_report, name='export_report'),
    path('manage/', views.custom_admin, name='custom_admin'),
    path('api/orders/', views.api_orders, name='api_orders'),
]
