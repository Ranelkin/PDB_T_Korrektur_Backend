import os, json, zipfile, glob, tempfile
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, WebSocket
from fastapi import Form
import uvicorn
from db.DB import db
from jose import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
from util.log_config import setup_logging
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from typing import List
import shutil
import secrets
from pydantic import BaseModel
from dotenv import load_dotenv 
from util.evaluator import evaluate
from util.review_spreadsheet import create_review_spreadsheet
#from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import FileResponse as StarletteFileResponse

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
logger = setup_logging("API")
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 10080
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

EXERCISE_TYPES = ["ER", "KEYS"]

class LoginCredentials(BaseModel):
    username: str
    password: str

app = FastAPI(
    title="PDB Korrektur API",
    description="Backend für die PDB Korrekturen",
    version="0.1.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# #For debugging purposes logs raw requests
# class LogRequestMiddleware(BaseHTTPMiddleware):
#     async def dispatch(self, request, call_next):
#         logger.info("Raw request headers: %s", request.headers)
#         body = await request.body()
#         logger.info("Raw request body: %s", body)
#         response = await call_next(request)
#         return response
#app.add_middleware(LogRequestMiddleware)

def create_access_token(data: dict):
    logger.debug("Creating access token with data: %s", data)
    to_encode = data.copy()
    expire = datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
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
async def login(credentials: LoginCredentials):
    username = credentials.username
    password = credentials.password
    user = db.get_user(username)
    if not user or not pwd_context.verify(password, user["password_hash"]):
        logger.warning("Login failed for user: %s", username)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": username})
    refresh_token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=30)
    db._execute_query('''
        UPDATE users 
        SET token = ?, expires_at = ? 
        WHERE email = ?
    ''', (refresh_token, expires_at.isoformat(), username))
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token
    }

@app.post("/refresh")
async def refresh_token(refresh_token: str = Form(...)):
    stored_token = db.get_refresh_token(refresh_token)
    if not stored_token or stored_token["expires"] < datetime.now():
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    username = stored_token["username"]
    new_access_token = create_access_token(data={"sub": username})
    return {"access_token": new_access_token, "token_type": "bearer"}

@app.post("/register/user")
async def register_user(username: str = Form(...), password: str = Form(...), role: str = Form(...)):
    try:
        userdata = {"username": username, "password": password, "role": role}
        db.register_user(userdata)
        for entry in EXERCISE_TYPES:
            os.makedirs(f"./data/{username}/{entry}/submission", exist_ok=True)
            os.makedirs(f"./data/{username}/{entry}/graded", exist_ok=True)
    except Exception as e:
        logger.error("Error creating user directories: %s", str(e))
        raise HTTPException(status_code=500, detail="Error registering user")
    return {"message": "User registered successfully"}

@app.post("/exercises/submit")
async def submit_exercises(
    exercise_type: str = Form(...),
    files: List[UploadFile] = File(...),
    current_user: str = Depends(get_current_user),
):
    if exercise_type not in EXERCISE_TYPES:
        logger.warning("Invalid exercise type: %s", exercise_type)
        raise HTTPException(status_code=400, detail="Invalid exercise type")

    if not files:
        logger.warning("No files provided by user: %s", current_user)
        raise HTTPException(status_code=400, detail="No files uploaded")

    UPLOAD_DIR = f"./data/{current_user}/{exercise_type}/submission"
    GRADED_DIR = f"./data/{current_user}/{exercise_type}/graded"
    SOLUTION_PATH = f"./solutions/"

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(GRADED_DIR, exist_ok=True)

    solution_data = None
    if exercise_type == "ER":
        if not os.path.exists(SOLUTION_PATH):
            logger.warning("Solution file not found: %s, skipping grading", SOLUTION_PATH)
        else:
            try:
                with open(SOLUTION_PATH, 'r') as sol_file:
                    solution_data = json.load(sol_file)
            except Exception as e:
                logger.error("Error loading solution file %s: %s", SOLUTION_PATH, str(e))
                raise HTTPException(status_code=500, detail=f"Failed to load solution file: {str(e)}")

    results = []
    uploaded_files = []
    temp_dir = tempfile.mkdtemp()  # Temporary directory for zip extraction

    for file in files:
        result = {
            "filename": file.filename,
            "safe_filename": None,
            "grading": None,
            "feedback_file": None,
            "status": "failed",
            "message": None
        }

        if file.size > 10 * 1024 * 1024:
            logger.warning("File too large: %s, user: %s", file.filename, current_user)
            result["message"] = f"File {file.filename} exceeds size limit"
            results.append(result)
            continue

        file_extension = file.filename.split(".")[-1].lower() if "." in file.filename else ""
        if file_extension not in ["json", "zip"]:
            logger.warning("Invalid file format: %s, user: %s", file.filename, current_user)
            result["message"] = f"File {file.filename} must be JSON or ZIP"
            results.append(result)
            continue

        try:
            if file_extension == "zip":
                # Save zip file temporarily
                zip_path = os.path.join(temp_dir, file.filename)
                with open(zip_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                logger.info("Zip file saved: %s for user: %s", file.filename, current_user)

                # Extract zip file
                extract_dir = os.path.join(temp_dir, file.filename.split(".")[0])
                os.makedirs(extract_dir, exist_ok=True)
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                logger.info("Zip file extracted to: %s", extract_dir)

                # Process JSON files in the zip
                json_files = glob.glob(os.path.join(extract_dir, "*.json"))
                for json_file in json_files:
                    safe_filename = os.path.basename(json_file)
                    file_path = os.path.join(UPLOAD_DIR, safe_filename)
                    shutil.copy(json_file, file_path)  # Copy to upload directory
                    logger.info("File copied to upload directory: %s", file_path)
                    uploaded_files.append(safe_filename)

                    # Evaluate and generate feedback
                    if exercise_type == "ER" and solution_data:
                        grading_result = evaluate(exercise_type, file_path, solution_data)
                        feedback_filename = f"{safe_filename.split('.')[0]}_Bewertung.xlsx"
                        create_review_spreadsheet(
                            grading_data=grading_result,
                            f_path=file_path,
                            filename=safe_filename,
                            exercise_type=exercise_type
                        )
                        logger.info("Feedback generated: %s for user: %s", feedback_filename, current_user)
                        result = {  # Create new result for each JSON file
                            "filename": safe_filename,
                            "safe_filename": safe_filename,
                            "grading": {
                                "total_points": grading_result.get("Gesamtpunktzahl", 0),
                                "max_points": grading_result.get("Erreichbare_punktzahl", 100),
                                "details": grading_result.get("details", {})
                            },
                            "feedback_file": feedback_filename,
                            "status": "success",
                            "message": "File processed and graded successfully"
                        }
                    else:
                        result = {
                            "filename": safe_filename,
                            "safe_filename": safe_filename,
                            "status": "success",
                            "message": "No grading performed due to missing solution file" if exercise_type == "ER" else "No grading available for this exercise type"
                        }
                    results.append(result)
            else:
                # Handle JSON file directly
                safe_filename = file.filename
                file_path = os.path.join(UPLOAD_DIR, safe_filename)
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                logger.info("File saved: %s for user: %s", safe_filename, current_user)
                uploaded_files.append(safe_filename)
                result["safe_filename"] = safe_filename

                if exercise_type == "ER" and solution_data:
                    grading_result = evaluate(exercise_type, file_path, solution_data)
                    feedback_filename = f"{safe_filename.split('.')[0]}_Bewertung.xlsx"
                    create_review_spreadsheet(
                        grading_data=grading_result,
                        f_path=file_path,
                        filename=safe_filename,
                        exercise_type=exercise_type
                    )
                    logger.info("Feedback generated: %s for user: %s", feedback_filename, current_user)
                    result.update({
                        "grading": {
                            "total_points": grading_result.get("Gesamtpunktzahl", 0),
                            "max_points": grading_result.get("Erreichbare_punktzahl", 100),
                            "details": grading_result.get("details", {})
                        },
                        "feedback_file": feedback_filename,
                        "status": "success",
                        "message": "File processed and graded successfully"
                    })
                else:
                    result.update({
                        "status": "success",
                        "message": "No grading performed due to missing solution file" if exercise_type == "ER" else "No grading available for this exercise type"
                    })
                results.append(result)
        except Exception as e:
            logger.error("Error processing file %s: %s", file.filename, str(e))
            result["message"] = f"Failed to process {file.filename}: {str(e)}"
            results.append(result)

    # Clean up temporary directory
    try:
        shutil.rmtree(temp_dir)
        logger.info("Cleaned up temporary directory: %s", temp_dir)
    except Exception as e:
        logger.warning("Error cleaning up temporary directory: %s", str(e))

    available_files = os.listdir(GRADED_DIR) if os.path.exists(GRADED_DIR) else []
    return {
        "message": "Files processed successfully",
        "user": current_user,
        "results": results,
        "uploaded_files": uploaded_files,
        "available_graded_files": available_files
    }
@app.websocket("/ws/depict-corrected-files")
async def depict_files(websocket: WebSocket, exercise_type: str, current_user: str = Depends(get_current_user)):
    await websocket.accept()
    try:
        import time
        time.sleep(3)  # Simulate processing delay
        graded_dir = f"./data/{current_user}/{exercise_type}/graded"
        available_files = os.listdir(graded_dir) if os.path.exists(graded_dir) else []
        logger.info(f"Available graded files for {current_user}/{exercise_type}: {available_files}")
        await websocket.send_json({"available_files": available_files})
        await websocket.close()
    except Exception as e:
        logger.error(f"Error in depict_files websocket: {str(e)}")
        await websocket.send_json({"error": str(e)})
        await websocket.close()

@app.get("/verify-token")
async def verify_token(current_user: str = Depends(get_current_user)):
    return {"username": current_user}

@app.get("/exercises/graded")
async def get_graded_exercises(
    type: str,
    current_user: str = Depends(get_current_user)
):
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

class CustomFileResponse(StarletteFileResponse):
    async def __call__(self, scope, receive, send):
        await super().__call__(scope, receive, send)
        if self.path and os.path.exists(self.path):
            try:
                os.remove(self.path)
                logger.info("Deleted temporary ZIP archive: %s", self.path)
            except Exception as e:
                logger.warning("Error deleting temporary ZIP archive: %s", str(e))

@app.get("/exercises/download")
async def download_feedback(
    exercise_type: str,
    current_user: str = Depends(get_current_user)
):
    """
    Endpoint to download all feedback files in the user's graded directory as a ZIP archive.

    Args:
        exercise_type (str): Type of exercise (e.g., 'ER', 'KEYS').
        current_user (str): Authenticated user identifier.

    Returns:
        FileResponse: A ZIP archive containing all feedback files.
    """
    if exercise_type not in EXERCISE_TYPES:
        logger.warning("Invalid exercise type: %s", exercise_type)
        raise HTTPException(status_code=400, detail="Invalid exercise type")

    # Define graded directory
    GRADED_DIR = f"./data/{current_user}/{exercise_type}/graded"
    if not os.path.exists(GRADED_DIR):
        logger.warning("Graded directory not found: %s for user: %s", GRADED_DIR, current_user)
        raise HTTPException(status_code=404, detail="No feedback files available")

    # Find all Excel files in the graded directory
    feedback_files = glob.glob(os.path.join(GRADED_DIR, "*.xlsx"))
    if not feedback_files:
        logger.warning("No feedback files found in: %s for user: %s", GRADED_DIR, current_user)
        raise HTTPException(status_code=404, detail="No feedback files available")

    # Create a temporary ZIP file
    timestamp = datetime.now().timestamp()
    zip_filename = f"{current_user}_{exercise_type}_feedback_{timestamp}.zip"
    temp_dir = tempfile.gettempdir()
    zip_path = os.path.join(temp_dir, zip_filename)

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in feedback_files:
                file_name = os.path.basename(file_path)
                zipf.write(file_path, arcname=file_name)
        logger.info("Created ZIP archive: %s with %d files for user: %s", zip_path, len(feedback_files), current_user)
    except Exception as e:
        logger.error("Error creating ZIP archive: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create ZIP archive: {str(e)}")

    # Serve the ZIP file with cleanup after response
    try:
        return CustomFileResponse(
            path=zip_path,
            filename=zip_filename,
            media_type="application/zip"
        )
    except Exception as e:
        logger.error("Error serving ZIP archive: %s", str(e))
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
                logger.info("Deleted temporary ZIP archive: %s", zip_path)
            except Exception as e:
                logger.warning("Error deleting temporary ZIP archive: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to serve ZIP archive: {str(e)}")

if __name__ == '__main__':
    logger.info("Starting API server")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )