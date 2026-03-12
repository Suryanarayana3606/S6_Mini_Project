import os
import joblib
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import transaction
from analytics.models import Product, Sales_Forecast, Sales_Transaction
from analytics.ml.features import fetch_and_prepare_data

MODEL_PATH = os.path.join(settings.BASE_DIR, 'analytics', 'ml', 'sales_model.pkl')

# Generate bounds roughly based on a fixed percentage or historical volatility
CONFIDENCE_INTERVAL = 0.15 # +/- 15%

def run_predictions(metrics=None):
    """
    Load trained model, generate future features, predict, and save to database.
    We'll predict 12 months ahead for each product.
    """
    if not os.path.exists(MODEL_PATH):
        print(f"Model not found at {MODEL_PATH}. Cannot run predictions.")
        return
        
    print("Loading model...")
    model = joblib.load(MODEL_PATH)
    
    # We need the most recent historical data to build the "lag" features
    df = fetch_and_prepare_data()
    if df.empty:
        print("No historical data available to build future features.")
        return
        
    products = Product.objects.all()
    
    # Clear old forecasts generated from this version to avoid duplicates
    Sales_Forecast.objects.all().delete()
    print("Cleared existing forecasts.")
    
    # Define how far ahead to predict
    HORIZON_MONTHS = 24
    # Determine the start month for forecasts (next month after max transaction date)
    max_date = Sales_Transaction.objects.latest('transaction_date').transaction_date
    start_date = max_date.replace(day=1) + relativedelta(months=1)
    
    # Default MAPE if we don't have metrics passed in
    mape = metrics['mape'] if metrics and 'mape' in metrics else 5.0
    
    new_forecasts = []
    
    print(f"Generating forecasts for {products.count()} products for {HORIZON_MONTHS} months from {start_date}...")
    
    # We will simulate a rolling forecast, updating the 'lag' features step-by-step
    for product in products:
        prod_id = product.product_id
        base_price = float(product.base_price)
        
        # Get the latest known data for this product
        prod_history = df[df['product_id'] == prod_id]
        
        if not prod_history.empty:
            lag_1 = prod_history.iloc[-1]['total_revenue']
            if len(prod_history) > 1:
                lag_2 = prod_history.iloc[-2]['total_revenue']
            else:
                lag_2 = 0
        else:
            lag_1 = 0
            lag_2 = 0
            
        current_date = start_date
        
        for i in range(HORIZON_MONTHS):
            # Create feature row for prediction
            features = pd.DataFrame([{
                'product_id': prod_id,
                'year': current_date.year,
                'month_num': current_date.month,
                'base_price': base_price,
                'lag_1_revenue': lag_1,
                'lag_2_revenue': lag_2
            }])
            
            # Predict
            pred_revenue = float(model.predict(features)[0])
            # Ensure no negative predictions
            pred_revenue = max(0.0, pred_revenue)
            
            lower_bound = pred_revenue * (1 - CONFIDENCE_INTERVAL)
            upper_bound = pred_revenue * (1 + CONFIDENCE_INTERVAL)
            
            # Save to list
            new_forecasts.append(Sales_Forecast(
                product=product,
                forecast_date=current_date,
                forecast_revenue=pred_revenue,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                model_version='XGBoost_v1.0',
                mape=mape
            ))
            
            # Shift lags for next step
            lag_2 = lag_1
            lag_1 = pred_revenue
            
            # Move to next month
            current_date += relativedelta(months=1)
            
    # Bulk insert for efficiency
    with transaction.atomic():
        Sales_Forecast.objects.bulk_create(new_forecasts)
        
    print(f"Successfully saved {len(new_forecasts)} forecasts to the database.")
