"""
seed_superadmin.py — Siembra el usuario superadmin inicial (idempotente).

El superadmin no pertenece a ningún tenant (tenant_id=NULL) y tiene
UserRole.SUPERADMIN. Requiere SUPERADMIN_EMAIL y SUPERADMIN_PASSWORD en el
entorno: no existe un password por defecto seguro, así que si faltan el
seed se omite sin bloquear el arranque (mismo criterio que JWT_SECRET_KEY
en auth/security.py, pero sin abortar el boot porque el login sin
superadmin sembrado sigue siendo un estado válido, solo no operable).

Spec: docs/specs/autenticacion-multiusuario-multitenant.md
Design: docs/designs/autenticacion-multitenant-design.md
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models
from auth.security import hash_password


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


if __name__ == "__main__":
    seed_superadmin()
