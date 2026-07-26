"""
create_pilot_users.py — One-off: creates the 3 pilot-tester accounts (Marie,
Marta/Mao, alk@3atlantic) as `admin` role inside the existing "Guepard"
tenant, so they share the same tenant/brand data for concurrency, feedback
and generation testing (Luis, 2026-07-26). Idempotent — safe to re-run,
skips users that already exist.

Not wired into main.py startup on purpose: these are named real people, not
generic seed/test fixtures (seed_test_users.py is at least opt-in via env
vars for that reason; this one has no boot-time trigger at all — it only
runs when explicitly invoked). Passwords are generated fresh per run and
printed ONCE to stdout — copy them out immediately and relay out of band
(no self-service invite-by-email flow exists yet, see
docs/specs/autenticacion-multiusuario-multitenant.md); they are not stored
anywhere else and cannot be recovered after this run.

Usage: python -m utils.create_pilot_users
"""
import os
import sys
import secrets
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


def create_pilot_users():
    db = SessionLocal()
    try:
        tenant = db.query(models.Tenant).filter(models.Tenant.name == DEFAULT_TENANT_NAME).first()
        if tenant is None:
            print(f"  [PilotUsers] ABORTED: tenant '{DEFAULT_TENANT_NAME}' not found — seed_default_tenant() must run first.")
            return

        for email in PILOT_USER_EMAILS:
            existing = db.query(models.User).filter(models.User.email == email).first()
            if existing:
                print(f"  [PilotUsers] Skipped (already exists): {email} (role={existing.role}, tenant_id={existing.tenant_id})")
                continue

            password = secrets.token_urlsafe(12)
            db.add(models.User(
                email=email,
                hashed_password=hash_password(password),
                role=models.UserRole.ADMIN.value,
                tenant_id=tenant.id,
                is_active=1,
            ))
            db.commit()
            print(f"  [PilotUsers] Created admin '{email}' in tenant '{tenant.name}' (id={tenant.id}) — password: {password}")
    except Exception as e:
        db.rollback()
        print(f"  [PilotUsers] ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    create_pilot_users()
