import os
from fastapi import FastAPI, HTTPException
from fastapi.params import Depends
import uvicorn  
from ..db.DB import db 
from jose import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
from ..util.log_config import setup_logging
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import FileResponse
from typing import Optional


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
logger = setup_logging("API")

SECRET_KEY = "your_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(
    title="PDB Korrektur API", 
    description="Backend für die PDB Korrekturen",
    version="0.1.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420"  ,"http://10.222.52.0/24" ],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)



def create_access_token(data: dict):
    logger.debug("Creating access token with data: %s", data)
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    logger.debug("Token expiration time set to: %s", expire)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    logger.info("Access token created")
    return token

def get_current_user(token: str = Depends(oauth2_scheme)):
    logger.debug("Decoding token: %s", token)
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        logger.debug("Token decoded successfully, username: %s", username)
        return username
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired: %s", token)
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError as e:
        logger.error("JWT decode error: %s", e)
        raise HTTPException(status_code=401, detail="Invalid credentials")


