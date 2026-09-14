from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(subject: str, role: str, division: str, token_type: str = "access") -> str:
    exp = datetime.now(UTC) + (timedelta(days=settings.refresh_token_days) if token_type == "refresh" else timedelta(minutes=settings.access_token_minutes))
    return jwt.encode({"sub": subject, "role": role, "division": division, "type": token_type, "exp": exp}, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
