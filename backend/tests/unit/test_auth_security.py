"""
test_auth_security.py — Hashing de password y JWT encode/decode (B2).

Spec: docs/specs/autenticacion-multiusuario-multitenant.md
"""
import datetime
import os
import subprocess
import sys

import pytest
from jose import JWTError, jwt

from auth import security


@pytest.mark.unit
class TestJwtSecretKeyRequired:

    def test_module_import_fails_without_jwt_secret_key(self):
        """
        Senior Reviewer, blocker #2: sin JWT_SECRET_KEY seteado, el módulo
        NO debe caer en un secreto hardcodeado — debe fallar el arranque.
        Corre en un subproceso aislado para no tocar el estado del módulo
        ya importado en el resto de la suite.
        """
        env = os.environ.copy()
        env.pop("JWT_SECRET_KEY", None)
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        result = subprocess.run(
            [sys.executable, "-c", "import auth.security"],
            cwd=backend_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode != 0
        assert "JWT_SECRET_KEY" in result.stderr


@pytest.mark.unit
class TestPasswordHashing:

    def test_hash_and_verify_roundtrip(self):
        hashed = security.hash_password("correct horse battery staple")
        assert hashed != "correct horse battery staple"
        assert security.verify_password("correct horse battery staple", hashed)

    def test_verify_rejects_wrong_password(self):
        hashed = security.hash_password("correct horse battery staple")
        assert not security.verify_password("wrong password", hashed)


@pytest.mark.unit
class TestAccessToken:

    def test_encodes_role_and_tenant_and_decodes_back(self):
        token = security.create_access_token(user_id=42, role="admin", tenant_id=7)
        payload = security.decode_token(token)
        assert payload["sub"] == "42"
        assert payload["role"] == "admin"
        assert payload["tenant_id"] == 7
        assert payload["type"] == "access"

    def test_superadmin_has_nullable_tenant_id(self):
        token = security.create_access_token(user_id=1, role="superadmin", tenant_id=None)
        payload = security.decode_token(token)
        assert payload["tenant_id"] is None

    def test_expired_token_fails_to_decode(self):
        now = datetime.datetime.utcnow()
        expired_payload = {
            "sub": "42", "role": "admin", "tenant_id": 7, "type": "access",
            "iat": now - datetime.timedelta(minutes=30),
            "exp": now - datetime.timedelta(minutes=15),
        }
        expired_token = jwt.encode(expired_payload, security.JWT_SECRET_KEY, algorithm=security.JWT_ALGORITHM)
        with pytest.raises(JWTError):
            security.decode_token(expired_token)

    def test_tampered_token_fails_to_decode(self):
        token = security.create_access_token(user_id=42, role="admin", tenant_id=7)
        # Voltea un carácter a mitad de la firma (último segmento tras el ".")
        # — cambiar el último carácter del token entero puede caer en un bit
        # de padding de base64url que no altera los bytes decodificados.
        header, payload, signature = token.split(".")
        mid = len(signature) // 2
        flipped_char = "A" if signature[mid] != "A" else "B"
        tampered_signature = signature[:mid] + flipped_char + signature[mid + 1:]
        tampered = f"{header}.{payload}.{tampered_signature}"
        with pytest.raises(JWTError):
            security.decode_token(tampered)

    def test_wrong_signing_key_fails_to_decode(self):
        payload = {"sub": "42", "role": "admin", "tenant_id": 7, "type": "access"}
        token = jwt.encode(payload, "a-different-secret", algorithm=security.JWT_ALGORITHM)
        with pytest.raises(JWTError):
            security.decode_token(token)


@pytest.mark.unit
class TestRefreshToken:

    def test_returns_token_jti_and_expiry(self):
        token, jti, expires_at = security.create_refresh_token(user_id=42)
        assert isinstance(jti, str) and len(jti) > 0
        assert expires_at > datetime.datetime.utcnow()
        payload = security.decode_token(token)
        assert payload["sub"] == "42"
        assert payload["jti"] == jti
        assert payload["type"] == "refresh"

    def test_two_calls_produce_different_jti(self):
        _, jti1, _ = security.create_refresh_token(user_id=42)
        _, jti2, _ = security.create_refresh_token(user_id=42)
        assert jti1 != jti2
