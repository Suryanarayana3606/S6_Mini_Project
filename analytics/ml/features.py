import pandas as pd
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from analytics.models import Sales_Transaction, Product

def get_historical_data():
    """
    Extract historical sales data from the database, aggregate by month and product.
    """
    # Aggregate revenue by month and product
    historical_data = list(
        Sales_Transaction.objects
        .annotate(month=TruncMonth('transaction_date'))
        .values('month', 'product_id')
        .annotate(total_revenue=Sum('revenue'))
        .order_by('product_id', 'month')
    )
    
    df = pd.DataFrame(historical_data)
    
    if df.empty:
        return df
        
    # Convert month to datetime and revenue to float
    df['month'] = pd.to_datetime(df['month'])
    df['total_revenue'] = df['total_revenue'].astype(float)
    
    return df

def prepare_features(df):
    """
    Prepare features for machine learning model.
    """
    if df.empty:
        return df
        
    # Extract date features Let's use Year, Month
    df['year'] = df['month'].dt.year
    df['month_num'] = df['month'].dt.month
    
    # Get product base prices
    products = Product.objects.all().values('product_id', 'base_price')
    products_df = pd.DataFrame(products)
    products_df['base_price'] = products_df['base_price'].astype(float)
    
    # Merge with base price
    df = df.merge(products_df, on='product_id', how='left')
    
    # Add some lag features to capture time series dependency
    # Make sure data is sorted chronologically per product
    df = df.sort_values(['product_id', 'month'])
    
    # Creating a 1-month lag feature
    df['lag_1_revenue'] = df.groupby('product_id')['total_revenue'].shift(1)
    # Creating a 2-month lag feature
    df['lag_2_revenue'] = df.groupby('product_id')['total_revenue'].shift(2)
    # Fill NaN for early months with the mean or 0, or drop them. 
    # Let's fill with 0 since it might be a new product
    df['lag_1_revenue'] = df['lag_1_revenue'].fillna(0)
    df['lag_2_revenue'] = df['lag_2_revenue'].fillna(0)
    
    return df

def fetch_and_prepare_data():
    """Main pipeline function for data preparation."""
    raw_df = get_historical_data()
    feature_df = prepare_features(raw_df)
    return feature_df
