import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from .config import utcnow
from .database import get_db
from .models import RefreshToken, User

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-this-secret")
if os.getenv("ENVIRONMENT", "development").lower() == "production":
    if SECRET_KEY == "dev-only-change-this-secret" or len(SECRET_KEY) < 32:
        raise RuntimeError("Set a unique SECRET_KEY of at least 32 characters in production.")
ALGORITHM = "HS256"
# Access tokens are short-lived (60 min): a leaked token is only useful for
# an hour, and the rotating 7-day refresh token keeps real sessions going.
# Override with ACCESS_TOKEN_EXPIRE_MINUTES if a deployment needs otherwise.
EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def hash_password(password):
    return pwd_context.hash(password)

def verify_password(password, hashed):
    return pwd_context.verify(password, hashed)

def create_access_token(user_id):
    expiry = datetime.now(timezone.utc) + timedelta(minutes=EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": expiry}, SECRET_KEY, algorithm=ALGORITHM)

def hash_token(token: str) -> str:
    """SHA-256 hex digest; only hashes are stored in the database."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def issue_refresh_token(db: Session, user_id: int) -> str:
    """Create and persist a refresh token; returns the plaintext token
    (shown to the client exactly once)."""
    token = secrets.token_urlsafe(48)
    db.add(RefreshToken(user_id=user_id, token_hash=hash_token(token),
                        expires_at=utcnow() + timedelta(days=REFRESH_EXPIRE_DAYS)))
    db.commit()
    return token

def revoke_all_refresh_tokens(db: Session, user_id: int) -> None:
    db.query(RefreshToken).filter_by(user_id=user_id, revoked=False).update({"revoked": True})
    db.commit()

def get_current_user(token=Depends(oauth2_scheme), db: Session=Depends(get_db)):
    error = HTTPException(401, "Invalid or expired token")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise error
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise error
    return user

def require_role(*roles):
    def checker(user=Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(403, "You do not have permission")
        return user
    return checker
