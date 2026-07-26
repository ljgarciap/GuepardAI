"""
create_pilot_users.py — One-off: creates (or resets) the 3 pilot-tester
accounts (Marie, Marta/Mao, alk@3atlantic) as `admin` role inside the
existing "Guepard" tenant, so they share the same tenant/brand data for
concurrency, feedback and generation testing (Luis, 2026-07-26).

Idempotent — safe to re-run. All 3 share one generic onboarding password
(PILOT_USER_PASSWORD, communicated to them directly by Luis) rather than a
random one per user, by explicit decision — they're expected to change it
immediately via the self-service /account page. Re-running this script
resets the password back to the generic one for any of the 3 that already
exist, in case one needs to be handed back out.

Not wired into main.py startup on purpose: these are named real people, not
generic seed/test fixtures (seed_test_users.py is at least opt-in via env
vars for that reason; this one has no boot-time trigger at all — it only
runs when explicitly invoked).

Usage: python -m utils.create_pilot_users
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models
from auth.security import hash_password
from utils.seed_superadmin import DEFAULT_TENANT_NAME

PILOT_USER_EMAILS = [
    "maosunae@gmail.com",
    "mariehay2015@gmail.com",
    "alk@3atlantic.com",
]

# Shared onboarding password — recipients are asked (in the same email that
# includes it) to change it via /account on first login.
PILOT_USER_PASSWORD = "Gu3p4rd_2026!"


def create_pilot_users():
    db = SessionLocal()
    try:
        tenant = db.query(models.Tenant).filter(models.Tenant.name == DEFAULT_TENANT_NAME).first()
        if tenant is None:
            print(f"  [PilotUsers] ABORTED: tenant '{DEFAULT_TENANT_NAME}' not found — seed_default_tenant() must run first.")
            return

        hashed = hash_password(PILOT_USER_PASSWORD)
        for email in PILOT_USER_EMAILS:
            existing = db.query(models.User).filter(models.User.email == email).first()
            if existing:
                existing.hashed_password = hashed
                existing.is_active = 1
                db.commit()
                print(f"  [PilotUsers] Reset password to the generic onboarding password: {email}")
                continue

            db.add(models.User(
                email=email,
                hashed_password=hashed,
                role=models.UserRole.ADMIN.value,
                tenant_id=tenant.id,
                is_active=1,
            ))
            db.commit()
            print(f"  [PilotUsers] Created admin '{email}' in tenant '{tenant.name}' (id={tenant.id}) with the generic onboarding password")
    except Exception as e:
        db.rollback()
        print(f"  [PilotUsers] ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    create_pilot_users()
