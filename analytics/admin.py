from django.contrib import admin

from django.contrib import admin
from .models import Customer, Product, Sales_Transaction, Sales_Forecast, FM_Customer_Segment

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('customer_id', 'customer_name', 'customer_type', 'industry', 'region', 'account_value')
    search_fields = ('customer_name', 'industry')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'product_name', 'category', 'base_price')
    search_fields = ('product_name', 'category')

@admin.register(Sales_Transaction)
class SalesTransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'transaction_date', 'customer', 'product', 'quantity', 'revenue')
    list_filter = ('transaction_date', 'customer__industry')
    
@admin.register(Sales_Forecast)
class SalesForecastAdmin(admin.ModelAdmin):
    list_display = ('forecast_id', 'product', 'forecast_date', 'forecast_revenue', 'model_version')
    list_filter = ('forecast_date', 'model_version')

@admin.register(FM_Customer_Segment)
class FMCustomerSegmentAdmin(admin.ModelAdmin):
    list_display = ('segment_id', 'customer', 'rfm_score', 'segment')
    list_filter = ('segment',)
