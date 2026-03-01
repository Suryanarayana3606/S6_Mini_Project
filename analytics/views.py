import csv
import json
from django.shortcuts import render
from django.http import HttpResponse
from django.db.models import Sum, Count, Avg
from .models import Customer, Product, Sales_Transaction, Sales_Forecast, FM_Customer_Segment

def dashboard_view(request):
    total_customers = Customer.objects.count()
    total_revenue = Sales_Transaction.objects.aggregate(Sum('revenue'))['revenue__sum'] or 0
    total_products = Product.objects.count()
    
    # Simple aggregated data for charts (mock logic: revenue by industry)
    revenue_by_industry = list(
        Sales_Transaction.objects.values('customer__industry')
        .annotate(total=Sum('revenue'))
        .order_by('-total')
    )
    
    chart_labels = [item['customer__industry'] for item in revenue_by_industry]
    chart_data = [float(item['total']) for item in revenue_by_industry]

    context = {
        'total_customers': total_customers,
        'total_revenue': total_revenue,
        'total_products': total_products,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
    }
    return render(request, 'analytics/dashboard.html', context)

def sales_forecast_view(request):
    forecasts = Sales_Forecast.objects.all().order_by('forecast_date')
    
    # Format data for chart
    dates = [f.forecast_date.strftime("%Y-%m-%d") for f in forecasts]
    revenues = [float(f.forecast_revenue) for f in forecasts]
    lower_bounds = [float(f.lower_bound) for f in forecasts]
    upper_bounds = [float(f.upper_bound) for f in forecasts]

    context = {
        'forecast_dates': json.dumps(dates),
        'forecast_revenues': json.dumps(revenues),
        'lower_bounds': json.dumps(lower_bounds),
        'upper_bounds': json.dumps(upper_bounds),
        'forecasts': forecasts,
    }
    return render(request, 'analytics/sales_forecast.html', context)

def segmentation_view(request):
    segments = FM_Customer_Segment.objects.all()
    
    segment_counts = list(
        FM_Customer_Segment.objects.values('segment')
        .annotate(count=Count('segment'))
        .order_by('-count')
    )
    
    labels = [s['segment'] for s in segment_counts]
    data = [s['count'] for s in segment_counts]

    context = {
        'segments': segments,
        'chart_labels': json.dumps(labels),
        'chart_data': json.dumps(data),
    }
    return render(request, 'analytics/segmentation.html', context)

def export_report_view(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sales_report.csv"'

    writer = csv.writer(response)
    writer.writerow(['Transaction ID', 'Date', 'Customer', 'Industry', 'Product', 'Quantity', 'Revenue'])

    transactions = Sales_Transaction.objects.select_related('customer', 'product').all()
    for txn in transactions:
        writer.writerow([
            txn.transaction_id,
            txn.transaction_date,
            txn.customer.customer_name,
            txn.customer.industry,
            txn.product.product_name,
            txn.quantity,
            txn.revenue
        ])

    return response
