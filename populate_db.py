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

    # 3. Create Sales Transactions (Past 1 Year)
    print("Creating Sales Transactions...")
    end_date = date(2025, 12, 31)
    # create about 800 transactions
    for _ in range(800):
        c = random.choice(customers)
        p = random.choice(products)
        qty = random.randint(1, 20)
        # random date in last 365 days from end of 2025
        days_ago = random.randint(0, 365)
        txn_date = end_date - timedelta(days=days_ago)
        
        # slight price variation
        actual_price = p.base_price * Decimal(random.uniform(0.9, 1.1))
        actual_price = round(actual_price, 2)
        revenue = actual_price * qty
        
        Sales_Transaction.objects.create(
            transaction_date=txn_date,
            customer=c,
            product=p,
            quantity=qty,
            unit_price=actual_price,
            revenue=revenue
        )

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
    # Calculate R,F,M from the transactions
    for c in customers:
        txns = Sales_Transaction.objects.filter(customer=c)
        if not txns.exists():
            continue
            
        latest_txn = txns.order_by('-transaction_date').first()
        recency_days = (end_date - latest_txn.transaction_date).days
        frequency = txns.count()
        monetary = txns.aggregate(Sum('revenue'))['revenue__sum'] or Decimal(0)
        
        # Simple scoring logic (1-5 where 5 is best)
        # Recency: lower is better (5 is best)
        if recency_days <= 30: r = 5
        elif recency_days <= 60: r = 4
        elif recency_days <= 90: r = 3
        elif recency_days <= 180: r = 2
        else: r = 1
            
        # Frequency: higher is better
        if frequency >= 20: f_s = 5
        elif frequency >= 15: f_s = 4
        elif frequency >= 10: f_s = 3
        elif frequency >= 5: f_s = 2
        else: f_s = 1
            
        # Monetary: higher is better
        if monetary >= 50000: m = 5
        elif monetary >= 30000: m = 4
        elif monetary >= 15000: m = 3
        elif monetary >= 5000: m = 2
        else: m = 1
            
        rfm = int(f"{r}{f_s}{m}")
        
        # Assign segment
        if r >= 4 and f_s >= 4 and m >= 4:
            seg = 'Champions'
        elif r >= 3 and f_s >= 3 and m >= 3:
            seg = 'Loyal Customers'
        elif r <= 2 and m >= 3:
            seg = 'At Risk'
        elif r >= 4 and f_s <= 2:
            seg = 'New Customers'
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
