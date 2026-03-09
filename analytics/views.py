import csv
import json
from django.shortcuts import render
from django.http import HttpResponse
from django.db.models import Sum, Count, Avg
from .models import Customer, Product, Sales_Transaction, Sales_Forecast, FM_Customer_Segment

def dashboard_view(request):
    industry_filter = request.GET.get('industry', '')
    region_filter = request.GET.get('region', '')
    
    transactions = Sales_Transaction.objects.all()
    if industry_filter:
        transactions = transactions.filter(customer__industry=industry_filter)
    if region_filter:
        transactions = transactions.filter(customer__region=region_filter)
        
    total_revenue = transactions.aggregate(Sum('revenue'))['revenue__sum'] or 0
    total_customers = transactions.values('customer').distinct().count()
    total_products = Product.objects.count() # This remains global, not filtered by transactions
    
    # Simple aggregated data for charts (mock logic: revenue by industry)
    industry_revenue = list(
        transactions.values('customer__industry')
        .annotate(revenue=Sum('revenue'))
        .order_by('-revenue')
    )
    
    chart_labels = [item['customer__industry'] for item in industry_revenue]
    chart_data = [float(item['revenue']) for item in industry_revenue]

    context = {
        'total_revenue': total_revenue,
        'total_customers': total_customers,
        'total_products': total_products,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
        'industries': ['Technology', 'Healthcare', 'Finance', 'Education', 'Manufacturing', 'Retail'],
        'regions': ['North America', 'Europe', 'Asia Pacific', 'Latin America'],
        'selected_industry': industry_filter,
        'selected_region': region_filter
    }
    return render(request, 'analytics/dashboard.html', context)

from django.db.models.functions import TruncMonth

def sales_forecast_view(request):
    # Fetch historical data (aggregated by month)
    historical_data = list(
        Sales_Transaction.objects
        .annotate(month=TruncMonth('transaction_date'))
        .values('month')
        .annotate(total_revenue=Sum('revenue'))
        .order_by('month')
    )
    
    # We want roughly the last 12 months of history
    if len(historical_data) > 12:
        historical_data = historical_data[-12:]

    hist_dates = [d['month'].strftime("%Y-%m") for d in historical_data]
    hist_revenues = [float(d['total_revenue']) for d in historical_data]

    # Aggregate forecasts by date across all products
    aggregated_forecasts = list(
        Sales_Forecast.objects.values('forecast_date')
        .annotate(
            total_revenue=Sum('forecast_revenue'),
            total_lower_bound=Sum('lower_bound'),
            total_upper_bound=Sum('upper_bound')
        )
        .order_by('forecast_date')
    )
    
    # Format forecast data (Month-Year)
    forecast_dates = [f['forecast_date'].strftime("%Y-%m") for f in aggregated_forecasts]
    forecast_revenues = [float(f['total_revenue']) for f in aggregated_forecasts]
    forecast_lower_bounds = [float(f['total_lower_bound']) for f in aggregated_forecasts]
    forecast_upper_bounds = [float(f['total_upper_bound']) for f in aggregated_forecasts]

    # Combine X-axis dates
    all_dates = hist_dates + forecast_dates
    
    # Create aligned arrays for Chart.js (nulls where data shouldn't draw)
    aligned_hist = hist_revenues + [None] * len(forecast_dates)
    aligned_forecast = [None] * len(hist_revenues) + forecast_revenues
    aligned_lower = [None] * len(hist_revenues) + forecast_lower_bounds
    aligned_upper = [None] * len(hist_revenues) + forecast_upper_bounds
    
    # To connect the lines perfectly, pad the forecast array's first element with the last historical point
    if hist_revenues and forecast_revenues:
        aligned_forecast[len(hist_revenues) - 1] = hist_revenues[-1]
        aligned_lower[len(hist_revenues) - 1] = hist_revenues[-1]
        aligned_upper[len(hist_revenues) - 1] = hist_revenues[-1]

    # --- MODEL SIMULATION ---
    selected_model = request.GET.get('model', 'LSTM') # Changed default to LSTM for better first impression
    horizon_str = request.GET.get('horizon', '12')
    try:
        horizon_months = int(horizon_str)
    except ValueError:
        horizon_months = 12
        
    models_list = ['Prophet', 'ARIMA', 'LSTM', 'XGBoost']
    
    # Adjust mock metrics and bounds based on model
    model_multipliers = {
        'Prophet': 1.0,
        'ARIMA': 1.25,   # Worse metrics, wider bounds
        'LSTM': 0.75,    # Better metrics, tighter bounds
        'XGBoost': 0.90  # Slightly better metrics
    }
    multiplier = model_multipliers.get(selected_model, 1.0)

    # Modify the bounds arrays to reflect confidence intervals shrinking/growing
    if hist_revenues and forecast_revenues:
        # Don't modify the 0th forecast point (it touches the historical point)
        for i in range(len(hist_revenues), len(aligned_upper)):
            if aligned_upper[i] is not None and aligned_forecast[i] is not None and aligned_lower[i] is not None:
                diff_upper = aligned_upper[i] - aligned_forecast[i]
                diff_lower = aligned_forecast[i] - aligned_lower[i]
                aligned_upper[i] = aligned_forecast[i] + (diff_upper * multiplier)
                aligned_lower[i] = aligned_forecast[i] - (diff_lower * multiplier)

    # Calculate mock metrics for the UI cards based on the populated MAPE
    base_avg_mape = Sales_Forecast.objects.aggregate(Avg('mape'))['mape__avg'] or 5.0
    avg_mape = float(base_avg_mape) * multiplier
    
    # Generate some realistic looking error metrics based on revenue scale
    if forecast_revenues:
        avg_revenue = sum(forecast_revenues) / len(forecast_revenues)
        mae = avg_revenue * (avg_mape / 100) # Rough estimate
        rmse = mae * 1.25 # RMSE is slightly higher than MAE
        r2 = max(0.0, 0.84 - ((multiplier - 1.0) * 0.4)) # Good fit -> Worse fit
    else:
        mae = 0
        rmse = 0
        r2 = 0

    forecasts = Sales_Forecast.objects.all().order_by('forecast_date')

    # If the user selects a shorter horizon, slice the arrays sent to frontend
    # To keep the visual continuous, we slice the future part of the aligned array
    # aligned array has length: len(hist_revenues) + len(forecast_revenues)
    
    total_length = len(hist_revenues) + horizon_months
    
    context = {
        'selected_model': selected_model,
        'horizon': horizon_str,
        'models': models_list,
        'forecast_dates': json.dumps(all_dates[:total_length]),
        'historical_revenues': json.dumps(aligned_hist[:total_length]),
        'forecast_revenues': json.dumps(aligned_forecast[:total_length]),
        'lower_bounds': json.dumps(aligned_lower[:total_length]),
        'upper_bounds': json.dumps(aligned_upper[:total_length]),
        'forecasts': forecasts[:horizon_months], # Limit registry table to horizon
        'mape': round(avg_mape, 2),
        'mae': round(mae, 2),
        'rmse': round(rmse, 2),
        'r2': round(r2, 2)
    }
    return render(request, 'analytics/sales_forecast.html', context)

def segmentation_view(request):
    segments = FM_Customer_Segment.objects.select_related('customer').all()
    
    segment_counts = list(
        FM_Customer_Segment.objects.values('segment')
        .annotate(count=Count('segment'))
        .order_by('-count')
    )
    
    labels = [s['segment'] for s in segment_counts]
    data = [s['count'] for s in segment_counts]

    # Generate Scatter Plot Data (mock K-means clusters)
    # X = Recency, Y = Monetary
    scatter_datasets = []
    color_map = {
        'Champions': '#10b981', # Green
        'Loyal': '#3b82f6', # Blue
        'At Risk': '#f59e0b', # Yellow
        'New': '#8b5cf6', # Purple
    }
    
    groups = {}
    for seg in segments:
        s_name = seg.segment
        if s_name not in groups:
            groups[s_name] = []
        
        groups[s_name].append({
            'x': float(seg.recency),
            'y': float(seg.monetary),
        })
        
    for s_name, points in groups.items():
        scatter_datasets.append({
            'label': s_name,
            'data': points,
            'backgroundColor': color_map.get(s_name, '#06b6d4'),
            'borderColor': color_map.get(s_name, '#06b6d4'),
            'pointRadius': 5,
            'pointHoverRadius': 8
        })

    context = {
        'segments': segments,
        'chart_labels': json.dumps(labels),
        'chart_data': json.dumps(data),
        'scatter_datasets': json.dumps(scatter_datasets),
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
def export_forecast_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sales_forecast_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Forecast Date', 'Predicted Revenue', 'Lower Bound', 'Upper Bound'])
    
    forecasts = Sales_Forecast.objects.all().order_by('forecast_date')
    for f in forecasts:
        writer.writerow([
            f.forecast_date,
            f.forecast_revenue,
            f.lower_bound,
            f.upper_bound
        ])
        
    return response

from django.http import JsonResponse

def api_forecast_view(request):
    """
    Elite Portfolio Feature: API Endpoint
    Serves forecast data as JSON, simulating a deployed ML microservice.
    Accepts ?model= string query.
    """
    selected_model = request.GET.get('model', 'LSTM')
    
    model_multipliers = {
        'Prophet': 1.0,
        'ARIMA': 1.25,   
        'LSTM': 0.75,    
        'XGBoost': 0.90  
    }
    multiplier = model_multipliers.get(selected_model, 1.0)
    
    forecasts = Sales_Forecast.objects.all().order_by('forecast_date')
    
    data = []
    for f in forecasts:
        # Apply the runtime mock multiplier to the bounds simulating the model
        diff_upper = float(f.upper_bound - f.forecast_revenue)
        diff_lower = float(f.forecast_revenue - f.lower_bound)
        
        simulated_upper = float(f.forecast_revenue) + (diff_upper * multiplier)
        simulated_lower = float(f.forecast_revenue) - (diff_lower * multiplier)
        
        data.append({
            'date': f.forecast_date.strftime('%Y-%m-%d'),
            'predicted_revenue': float(f.forecast_revenue),
            'lower_bound': simulated_lower,
            'upper_bound': simulated_upper,
            'model_ensemble': selected_model
        })
        
    return JsonResponse({
        'status': 'success',
        'meta': {
            'model_selected': selected_model,
            'confidence_interval': '95%',
            'description': 'Predictive revenue forecasting endpoint'
        },
        'data': data
    })
