
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
from fastapi import Form

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
logger = setup_logging("API")

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 10080
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

EXERCISE_TYPES = ["ER", "KEYS"]

app = FastAPI(
    title="PDB Korrektur API", 
    description="Backend für die PDB Korrekturen",
    version="0.1.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

def create_access_token(data: dict):
    logger.debug("Creating access token with data: %s", data)
    to_encode = data.copy()
    expire = datetime.now(datetime.timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
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

def get_current_admin_user(current_user: dict = Depends(get_current_user)):
    if "admin" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    user = db.get_user(username)  
    if not user or not pwd_context.verify(password, user["hashed_password"]):
        logger.warning("Login failed for user: %s", username)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/refresh")
async def refresh_token(refresh_token: str = Form(...)):
    stored_token = db.get_refresh_token(refresh_token)  # Validate against DB
    if not stored_token or stored_token["expires"] < datetime.now(datetime.timezone.utc):
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    username = stored_token["username"]
    new_access_token = create_access_token(data={"sub": username})
    return {"access_token": new_access_token, "token_type": "bearer"}


@app.post("/register/user")
async def register_user(username: str, password: str, role: str): 
    """This endpoint creates the directorys where each tutor submits their
    submissions and the graded exercises get discarded 

    Args:
        username (str): username
        password (str): password
        role (str): Either admin / or tutor
    """
    try: 
        userdata = {"username": username, "password": password, "role": role}
        db.register_user(userdata)
        for entry in EXERCISE_TYPES:
            os.mkdir(f"./data/"+username+"/"+entry)
            os.mkdir(f"./data/"+username+"/"+entry+"/submission") 
            os.mkdir(f"./data/"+username+"/"+entry+"/graded")
    except os.error as e: 
        logger.error("Error creating user directories: ", e)
        raise HTTPException(status_code=401, detail="Error registering user")
    
    