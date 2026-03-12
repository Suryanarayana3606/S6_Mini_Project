import os
import django
import random
from datetime import date, timedelta
from faker import Faker
from decimal import Decimal

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from analytics.models import Customer, Product, Sales_Transaction, Sales_Forecast, FM_Customer_Segment
from django.db.models import Sum
from django.db import transaction

fake = Faker()

@transaction.atomic
def populate_db():
    print("Clearing old data...")
    Customer.objects.all().delete()
    Product.objects.all().delete()
    
    # 1. Create Products
    categories = ['Software', 'Hardware', 'Services', 'Consulting']
    print("Creating Products...")
    products = []
    for _ in range(15):
        p = Product.objects.create(
            product_name=fake.company() + " " + fake.word().capitalize() + " System",
            category=random.choice(categories),
            base_price=Decimal(random.randint(500, 5000))
        )
        products.append(p)
        
    # 2. Create Customers
    industries = ['Technology', 'Healthcare', 'Finance', 'Education', 'Manufacturing', 'Retail']
    regions = ['North America', 'Europe', 'Asia Pacific', 'Latin America']
    types = ['Enterprise', 'Mid-Market', 'SMB']
    
    print("Creating Customers...")
    customers = []
    for _ in range(50):
        c = Customer.objects.create(
            customer_name=fake.company(),
            customer_type=random.choice(types),
            industry=random.choice(industries),
            region=random.choice(regions),
            account_value=Decimal(random.randint(10000, 500000))
        )
        customers.append(c)

    # 3. Create Sales Transactions (Past 3 Years for better ML training)
    print("Creating Realistic Sales Transactions (3 Years)...")
    
    # Create non-uniform distribution of customer weights (Zipf/Pareto-like)
    customer_weights = [1.0 / (i + 1)**1.2 for i in range(len(customers))]
    random.shuffle(customer_weights)
    end_date = date(2025, 12, 31)
    start_date = end_date - timedelta(days=3*365)
    
    import math
    
    transactions_to_create = []
    
    # Pre-calculate daily base volume for each product
    product_profiles = {}
    for p in products:
        # Give each product a unique baseline volume and seasonality offset
        base_daily_sales = random.uniform(0.5, 3.0) 
        seasonality_shift = random.uniform(0, math.pi * 2) # Peak at different times of year
        growth_rate = random.uniform(0.0005, 0.002) # Daily growth trend
        product_profiles[p.product_id] = {
            'base': base_daily_sales,
            'shift': seasonality_shift,
            'growth': growth_rate,
            'product': p
        }

    current_date = start_date
    day_index = 0
    
    while current_date <= end_date:
        # Day of year (1-365) for seasonality
        day_of_year = current_date.timetuple().tm_yday
        seasonality_angle = (day_of_year / 365.0) * 2 * math.pi
        
        for p_id, profile in product_profiles.items():
            p = profile['product']
            
            # 1. Base volume
            volume = profile['base']
            
            # 2. Add linear trend (business growing over 3 years)
            trend = day_index * profile['growth']
            
            # 3. Add seasonality (sine wave peaking at specific times of year)
            season = math.sin(seasonality_angle + profile['shift']) * (profile['base'] * 0.8)
            
            # 4. Add some noise/randomness
            noise = random.uniform(-0.5, 0.5)
            
            # Calculate expected sales for this product today
            expected_qty = volume + trend + season + noise
            
            # Convert to actual integer sales (sometimes 0, sometimes multiple items)
            # Use Poisson-like logic (simplified):
            if expected_qty > 0:
                # 70% chance to actually have a sale on a given day if expected > 0
                if random.random() < 0.70:
                    # Randomize quantity around the expected value
                    qty = max(1, int(random.gauss(expected_qty, expected_qty * 0.2)))
                    c = random.choices(customers, weights=customer_weights)[0]
                    
                    # Slight price variation
                    actual_price = float(p.base_price) * random.uniform(0.95, 1.05)
                    revenue = actual_price * qty
                    
                    transactions_to_create.append(Sales_Transaction(
                        transaction_date=current_date,
                        customer=c,
                        product=p,
                        quantity=qty,
                        unit_price=actual_price,
                        revenue=revenue
                    ))
        
        current_date += timedelta(days=1)
        day_index += 1
        
        # Insert in batches to prevent memory issues
        if len(transactions_to_create) >= 5000:
            Sales_Transaction.objects.bulk_create(transactions_to_create)
            transactions_to_create = []

    # Insert any remaining transactions
    if transactions_to_create:
        Sales_Transaction.objects.bulk_create(transactions_to_create)


    # 4. Create Sales Forecasts (Next 3 months, roughly 90 days from Jan 1 2026)
    print("Creating Sales Forecasts...")
    start_forecast = date(2026, 1, 1)
    
    for p in products:
        # Calculate historical baseline from the last 30 days of 2025
        thirty_days_ago = end_date - timedelta(days=30)
        recent_txns = Sales_Transaction.objects.filter(product=p, transaction_date__gte=thirty_days_ago)
        
        if recent_txns.exists():
            historical_total = sum(t.revenue for t in recent_txns)
            base_daily_revenue = float(historical_total) / 30.0
        else:
            # Fallback if no recent transactions exist for a product
            base_daily_revenue = float(p.base_price) * random.uniform(0.5, 2.0)
            
        # We want to forecast for 12 months
        import math
        for month_offset in range(12):
            target_month = start_forecast.month + month_offset
            target_year = start_forecast.year + (target_month - 1) // 12
            target_month = (target_month - 1) % 12 + 1
            f_date = date(target_year, target_month, 1)
            
            # Since baseline was daily, scale to monthly (approx x30)
            base_monthly_revenue = base_daily_revenue * 30.0
            
            # Predict based on historical average with a mild trend
            trend = month_offset * (base_monthly_revenue * 0.02) # Milder linear upward trend
            
            # 12-month annual cycle
            seasonality_angle = (month_offset / 12.0) * 2 * math.pi
            seasonality = (base_monthly_revenue * 0.25) * math.sin(seasonality_angle)
            
            # Random noise (± 10%)
            noise = random.uniform(-0.10, 0.10) * base_monthly_revenue
            
            f_rev = base_monthly_revenue + trend + seasonality + noise
            f_rev = max(float(p.base_price) * 3.0, f_rev) # Should not drop below a fraction of base price per month
            
            lower_b = f_rev * random.uniform(0.80, 0.90)
            upper_b = f_rev * random.uniform(1.10, 1.20)
            
            Sales_Forecast.objects.create(
                product=p,
                forecast_date=f_date,
                forecast_revenue=Decimal(round(f_rev, 2)),
                lower_bound=Decimal(round(lower_b, 2)),
                upper_bound=Decimal(round(upper_b, 2)),
                model_version='v3.0-HistoryAnchored',
                mape=Decimal(round(random.uniform(2.0, 6.0), 2))
            )

    # 5. Create FM Customer Segments
    print("Calculating and Creating FM Customer Segments...")
    import pandas as pd
    
    rfm_data = []
    
    # Calculate R,F,M from the transactions
    for c in customers:
        txns = Sales_Transaction.objects.filter(customer=c)
        if not txns.exists():
            continue
            
        latest_txn = txns.order_by('-transaction_date').first()
        recency_days = (end_date - latest_txn.transaction_date).days
        frequency = txns.count()
        monetary = txns.aggregate(Sum('revenue'))['revenue__sum'] or Decimal(0)
        
        rfm_data.append({
            'customer': c,
            'recency': recency_days,
            'frequency': frequency,
            'monetary': float(monetary)
        })
        
    if rfm_data:
        df_rfm = pd.DataFrame(rfm_data)
        
        # Rank scores (1 to 5) using quantiles
        df_rfm['r_rank'] = df_rfm['recency'].rank(method='first', ascending=False)
        df_rfm['f_rank'] = df_rfm['frequency'].rank(method='first', ascending=True)
        df_rfm['m_rank'] = df_rfm['monetary'].rank(method='first', ascending=True)
        
        df_rfm['r_score'] = pd.qcut(df_rfm['r_rank'], 5, labels=[1, 2, 3, 4, 5])
        df_rfm['f_score'] = pd.qcut(df_rfm['f_rank'], 5, labels=[1, 2, 3, 4, 5])
        df_rfm['m_score'] = pd.qcut(df_rfm['m_rank'], 5, labels=[1, 2, 3, 4, 5])
        
        for _, row in df_rfm.iterrows():
            c = row['customer']
            recency_days = int(row['recency'])
            frequency = int(row['frequency'])
            monetary = Decimal(row['monetary'])
            r = int(row['r_score'])
            f_s = int(row['f_score'])
            m = int(row['m_score'])
            
            rfm = int(f"{r}{f_s}{m}")
            
            # Assign segment
            if r >= 4 and f_s >= 4 and m >= 4:
                seg = 'Champions'
            elif r >= 3 and f_s >= 3 and m >= 3:
                seg = 'Loyal'
            elif r <= 2 and m >= 3:
                seg = 'At Risk'
            elif r >= 4 and f_s <= 2:
                seg = 'New'
            elif r <= 2 and f_s <= 2:
                seg = 'Lost'
            else:
                seg = 'Promising'
                
            FM_Customer_Segment.objects.create(
                customer=c,
                recency=recency_days,
                frequency=frequency,
                monetary=monetary,
                r_score=r,
                f_score=f_s,
                m_score=m,
                rfm_score=rfm,
                segment=seg
            )

    print("Database population complete!")

if __name__ == "__main__":
    populate_db()
