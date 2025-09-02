"""Configuration module for app.py. 
Everything that is used globaly/ is a helper method 
should be stored in this module
"""
import os

from util.log_config import setup_logging
from datetime import datetime, timedelta
from jose import jwt
from fastapi import HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from db.database import db
from passlib.context import CryptContext
from fastapi import Query

__author__ = 'Ranel Karimov, ranelkin@icloud.com'

logger = setup_logging("api_util")
#Config params 
ACCESS_TOKEN_EXPIRE_MINUTES = 10080
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"

# Security setup
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

#Authentication methods
def create_access_token(data: dict) -> str:
    """Create a JWT access token with expiration."""
    logger.debug("Creating access token with data: %s", data)
    to_encode = data.copy()
    expire = datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    logger.info("Access token created")
    return token

def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """Decode JWT token and return username."""
    logger.debug("Decoding token")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        logger.debug("Token decoded successfully, username: %s", username)
        if not username:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return username
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError as e:
        logger.error("JWT decode error: %s", str(e))
        raise HTTPException(status_code=401, detail="Invalid credentials")

def get_current_admin_user(current_user: str = Depends(get_current_user)) -> str:
    """Verify if user has admin role."""
    user = db.get_user(current_user)
    if "admin" not in user.get("roles", []):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


async def get_current_user_websocket(token: str = Query(...)) -> str:
    """
    WebSocket-specific authentication that takes token as a query parameter.
    WebSockets don't have headers like HTTP requests, so we use query params.
    """
    logger.debug("Authenticating WebSocket connection")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        logger.debug("WebSocket token decoded successfully, username: %s", username)
        if not username:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return username
    except jwt.ExpiredSignatureError:
        logger.warning("WebSocket token expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError as e:
        logger.error("WebSocket JWT decode error: %s", str(e))
        raise HTTPException(status_code=401, detail="Invalid credentials")
