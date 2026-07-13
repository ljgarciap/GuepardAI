"""
seed_superadmin.py — Siembra el estado mínimo de plataforma: el superadmin
inicial y el tenant base "Guepard" (ambos idempotentes).

El superadmin no pertenece a ningún tenant (tenant_id=NULL) y tiene
UserRole.SUPERADMIN. Requiere SUPERADMIN_EMAIL y SUPERADMIN_PASSWORD en el
entorno: no existe un password por defecto seguro, así que si faltan el
seed se omite sin bloquear el arranque (mismo criterio que JWT_SECRET_KEY
en auth/security.py, pero sin abortar el boot porque el login sin
superadmin sembrado sigue siendo un estado válido, solo no operable).

El tenant "Guepard" (DEFAULT_TENANT_NAME) es el único tenant que el arranque
siembra por defecto — decisión de Luis 2026-07-12: la DB debe quedar en un
estado mínimo y determinístico (superadmin + un tenant, nada más) para poder
validar que todo se pueda cargar bien desde cero, sin acumular tenants/datos
de demo. `seed_test_users.py` (opt-in, ver ese archivo) se asocia a este
mismo tenant en vez de crear el suyo propio.

Spec: docs/specs/autenticacion-multiusuario-multitenant.md
Design: docs/designs/autenticacion-multitenant-design.md
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models
from auth.security import hash_password

DEFAULT_TENANT_NAME = "Guepard"


def seed_superadmin():
    email = os.getenv("SUPERADMIN_EMAIL")
    password = os.getenv("SUPERADMIN_PASSWORD")
    if not email or not password:
        print("  [Seed] Skipped superadmin: SUPERADMIN_EMAIL/SUPERADMIN_PASSWORD no configurados.")
        return

    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(models.User.email == email).first()
        if existing:
            print(f"  [Seed] Skipped superadmin (already exists): {email}")
            return

        db.add(models.User(
            email=email,
            hashed_password=hash_password(password),
            role=models.UserRole.SUPERADMIN.value,
            tenant_id=None,
            is_active=1,
        ))
        db.commit()
        print(f"  [Seed] Inserted superadmin: {email}")
    except Exception as e:
        db.rollback()
        print(f"  [Seed] ERROR seeding superadmin: {e}")
        raise
    finally:
        db.close()


def seed_default_tenant():
    # Mismo gate que seed_superadmin(): sin esto, importar main.py (lo que hace
    # CUALQUIER test que use `from main import app`) sembraba un tenant "Guepard"
    # real en cualquier DB que SessionLocal apunte en ese momento — incluida la
    # DB de test, donde el schema no se resetea entre archivos de test y esa fila
    # quedaba pisando el resto de la sesión de pytest (bug encontrado 2026-07-12
    # al correr la suite completa: FK violation al limpiar el tenant en el
    # fixture de test_seed_platform_bootstrap.py). SUPERADMIN_EMAIL nunca está
    # seteado en .env.test a propósito — este gate lo aprovecha en vez de
    # inventar uno nuevo.
    if not os.getenv("SUPERADMIN_EMAIL") or not os.getenv("SUPERADMIN_PASSWORD"):
        print("  [Seed] Skipped default tenant: SUPERADMIN_EMAIL/SUPERADMIN_PASSWORD no configurados.")
        return

    db = SessionLocal()
    try:
        existing = db.query(models.Tenant).filter(models.Tenant.name == DEFAULT_TENANT_NAME).first()
        if existing:
            print(f"  [Seed] Skipped default tenant (already exists): {DEFAULT_TENANT_NAME}")
            return

        db.add(models.Tenant(name=DEFAULT_TENANT_NAME))
        db.commit()
        print(f"  [Seed] Inserted default tenant: {DEFAULT_TENANT_NAME}")
    except Exception as e:
        db.rollback()
        print(f"  [Seed] ERROR seeding default tenant: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_superadmin()
    seed_default_tenant()
