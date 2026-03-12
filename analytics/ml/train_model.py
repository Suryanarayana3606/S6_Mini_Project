import os
import joblib
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, mean_absolute_percentage_error
from xgboost import XGBRegressor
from django.conf import settings
from analytics.ml.features import fetch_and_prepare_data

MODEL_PATH = os.path.join(settings.BASE_DIR, 'analytics', 'ml', 'sales_model.pkl')

def train_and_save_model():
    """Trains a sales forecasting model and saves it to disk."""
    print("Fetching and preparing data for training...")
    df = fetch_and_prepare_data()
    
    if df.empty or len(df) < 10:
        print("Not enough data to train a model.")
        return None
        
    print(f"Data prepared. {len(df)} records found.")
    
    # Define features and target
    features = ['product_id', 'year', 'month_num', 'base_price', 'lag_1_revenue', 'lag_2_revenue']
    X = df[features]
    y = df['total_revenue']
    
    # Train/Test Split (Time-based or random)
    # Using random split for simplicity, but time-based is usually better for forecasting
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    print("Training XGBoost Regressor...")
    model = XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=5, random_state=42)
    model.fit(X_train, y_train)
    
    # Evaluate
    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    from sklearn.metrics import root_mean_squared_error
    rmse = root_mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    mape = mean_absolute_percentage_error(y_test, y_pred) * 100
    
    print("\n--- Model Evaluation Metrics ---")
    print(f"MAE:  {mae:.2f}")
    print(f"RMSE: {rmse:.2f}")
    print(f"R²:   {r2:.2f}")
    print(f"MAPE: {mape:.2f}%")
    print("--------------------------------\n")
    
    # Save the model
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")
    
    return {
        'mae': mae,
        'rmse': rmse,
        'r2': r2,
        'mape': mape
    }
