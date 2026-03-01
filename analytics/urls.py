from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('sales-forecast/', views.sales_forecast_view, name='sales_forecast'),
    path('segmentation/', views.segmentation_view, name='segmentation'),
    path('export/', views.export_report_view, name='export_report'),
]
