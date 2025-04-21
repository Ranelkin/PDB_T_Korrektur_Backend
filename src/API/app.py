
import os
from fastapi import FastAPI, HTTPException, UploadFile, File 
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
from typing import Optional, List
from fastapi import Form
import shutil

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
async def login(credentials):
    username, password = credentials['username'], credentials['password']
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
    
    
    
@app.post("/exercises/submit")
async def submit_exercises(
    exercise_type, 
    files: List[UploadFile] = File(...),  
    current_user: str = Depends(get_current_user), 
):
    """
    Upload multiple exercise files and store them on the server.
    """
    UPLOAD_DIR = "./data/"
    UPLOAD_DIR = UPLOAD_DIR +exercise_type + "/"
    if not files:
        logger.warning("No files provided by user: %s", current_user)
        raise HTTPException(status_code=400, detail="No files uploaded")

    saved_files = []
    for file in files:
        #Validate file (e.g., size, type)
        if file.size > 10 * 1024 * 1024:  #Limit to 10MB
            logger.warning("File too large: %s, user: %s", file.filename, current_user)
            raise HTTPException(status_code=400, detail=f"File {file.filename} exceeds size limit")

        # Define a unique file path (e.g., using timestamp or UUID)
        file_extension = file.filename.split(".")[-1] if "." in file.filename else ""
        safe_filename = f"{current_user}_{datetime.utcnow().timestamp()}.{file_extension}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)

        # Save the file
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)  
            saved_files.append(safe_filename)
            logger.info("File saved: %s for user: %s", safe_filename, current_user)
        except Exception as e:
            logger.error("Error saving file %s: %s", file.filename, str(e))
            raise HTTPException(status_code=500, detail=f"Failed to save {file.filename}")

    return {
        "message": "Files uploaded successfully",
        "uploaded_files": saved_files,
        "user": current_user
    }

# Add these endpoints to your existing app.py

@app.get("/verify-token")
async def verify_token(current_user: str = Depends(get_current_user)):
    """
    Verify if the provided token is valid
    """
    return {"username": current_user}

@app.get("/exercises/graded")
async def get_graded_exercises(
    type: str,
    current_user: str = Depends(get_current_user)
):
    """
    Get a list of graded exercise files for a specific type
    """
    try:
        graded_dir = f"./data/{current_user}/{type}/graded"
        files = []
        
        if os.path.exists(graded_dir):
            for filename in os.listdir(graded_dir):
                file_path = os.path.join(graded_dir, filename)
                if os.path.isfile(file_path):
                    files.append({
                        "name": filename,
                        "size": os.path.getsize(file_path)
                    })
        
        return {"files": files}
    except Exception as e:
        logger.error(f"Error getting graded files: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving graded files")

@app.get("/exercises/download")
async def download_file(
    filename: str,
    type: str,
    current_user: str = Depends(get_current_user)
):
    """
    Download a specific graded exercise file
    """
    file_path = f"./data/{current_user}/{type}/graded/{filename}"
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/octet-stream'
    )
    
if __name__ == '__main__': 
    logger.info("Starting API server")
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True  
    )