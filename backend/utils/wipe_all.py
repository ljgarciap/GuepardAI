import sys
import os

# Allow imports from backend/ when running this script
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models

from database import engine

try:
    print("Truncating all user data (CASCADE)...")
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE brands CASCADE;"))
        conn.commit()
    
    print("Seeding default data...")
    from seed import seed_data
    seed_data()
    
    print("Database completely wiped, recreated, and seeded!")
except Exception as e:
    print(f"Error wiping database: {e}")
