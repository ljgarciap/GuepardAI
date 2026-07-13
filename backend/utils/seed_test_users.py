"""
seed_test_users.py — Siembra usuarios de prueba (admin + cliente) para QA
manual, asociados al tenant base ("Guepard", ver seed_superadmin.py).
Idempotente y deshabilitado por defecto.

Solo corre si TEST_ADMIN_EMAIL/TEST_ADMIN_PASSWORD están seteados. A
propósito NO se setean en el .env de EC2 — este seed nunca debe crear
cuentas en producción real, aunque el código viva en `master` (mismo
criterio de "requiere env var explícita" que seed_superadmin.py, pero acá
la intención es que el `.env` de producción JAMÁS las tenga).

Ajuste 2026-07-12: ya NO crea su propio tenant ("Test Organization") — se
asocia al tenant base que siembra seed_default_tenant(), para que la DB no
acumule tenants de demo (decisión de Luis: solo superadmin + un tenant).
Requiere que seed_default_tenant() haya corrido antes (main.py lo garantiza
en el orden de arranque); si el tenant base no existe todavía, se salta con
un warning en vez de crear uno propio.

Spec: docs/specs/autenticacion-multiusuario-multitenant.md
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models
from auth.security import hash_password
from utils.seed_superadmin import DEFAULT_TENANT_NAME


def seed_test_users():
    admin_email = os.getenv("TEST_ADMIN_EMAIL")
    admin_password = os.getenv("TEST_ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        print("  [Seed] Skipped test users: TEST_ADMIN_EMAIL/TEST_ADMIN_PASSWORD no configurados.")
        return

    db = SessionLocal()
    try:
        admin = db.query(models.User).filter(models.User.email == admin_email).first()
        if admin is None:
            tenant_name = os.getenv("TEST_TENANT_NAME", DEFAULT_TENANT_NAME)
            tenant = db.query(models.Tenant).filter(models.Tenant.name == tenant_name).first()
            if tenant is None:
                print(f"  [Seed] Skipped test users: tenant '{tenant_name}' not found — seed_default_tenant() must run first.")
                return
            admin = models.User(
                email=admin_email,
                hashed_password=hash_password(admin_password),
                role=models.UserRole.ADMIN.value,
                tenant_id=tenant.id,
                is_active=1,
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            print(f"  [Seed] Inserted test admin: {admin_email}")
        else:
            print(f"  [Seed] Skipped test admin (already exists): {admin_email}")

        cliente_email = os.getenv("TEST_CLIENTE_EMAIL")
        cliente_password = os.getenv("TEST_CLIENTE_PASSWORD")
        if not cliente_email or not cliente_password:
            print("  [Seed] Skipped test cliente: TEST_CLIENTE_EMAIL/TEST_CLIENTE_PASSWORD no configurados.")
            return

        cliente = db.query(models.User).filter(models.User.email == cliente_email).first()
        if cliente is None:
            cliente = models.User(
                email=cliente_email,
                hashed_password=hash_password(cliente_password),
                role=models.UserRole.CLIENTE.value,
                tenant_id=admin.tenant_id,
                is_active=1,
            )
            db.add(cliente)
            db.commit()
            print(f"  [Seed] Inserted test cliente: {cliente_email}")
        else:
            print(f"  [Seed] Skipped test cliente (already exists): {cliente_email}")
    except Exception as e:
        db.rollback()
        print(f"  [Seed] ERROR seeding test users: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_test_users()
