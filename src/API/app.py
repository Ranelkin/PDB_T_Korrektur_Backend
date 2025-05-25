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
from typing import List, Optional, Dict
import shutil
import secrets
from pydantic import BaseModel
from dotenv import load_dotenv 
from util.evaluator import evaluate
from util.review_spreadsheet import create_review_spreadsheet
from starlette.responses import FileResponse as StarletteFileResponse

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
logger = setup_logging("API")
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 10080
MAX_FILE_SIZE = 1024 * 1024 * 5     #5MB File size Limit 
ALLOWED_EXTENSIONS = ["zip", "json"]

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

def setup_directories(current_user: str, exercise_type: str) -> tuple[str, str, str]:
    upload_dir = f"./data/{current_user}/{exercise_type}/submission"
    graded_dir = f"./data/{current_user}/{exercise_type}/graded"
    solution_dir = "./solutions/"
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(graded_dir, exist_ok=True)
    return upload_dir, graded_dir, solution_dir

def validate_file(file: UploadFile) -> tuple[Optional[str], Dict]:
    result = {
        "filename": file.filename,
        "safe_filename": None,
        "grading": None,
        "feedback_file": None,
        "status": "failed",
        "message": None
    }

    if file.size > MAX_FILE_SIZE:
        result["message"] = f"File {file.filename} exceeds size limit"
        logger.warning("File too large: %s", file.filename)
        return None, result

    file_extension = file.filename.split(".")[-1].lower() if "." in file.filename else ""
    if file_extension not in ALLOWED_EXTENSIONS:
        result["message"] = f"File {file.filename} must be JSON or ZIP"
        logger.warning("Invalid file format: %s", file.filename)
        return None, result

    return file_extension, result

def save_submission_to_directory(file: UploadFile, submission_name: str, upload_dir: str, temp_dir: str) -> str:
    """Save submission to upload directory (flat structure) and return temp path for processing"""
    # Save original file to upload directory (flat structure, no subdirectories)
    file_path = os.path.join(upload_dir, file.filename)
    file.file.seek(0)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Also save to temp directory for processing
    temp_submission_dir = os.path.join(temp_dir, submission_name)
    os.makedirs(temp_submission_dir, exist_ok=True)
    temp_file_path = os.path.join(temp_submission_dir, file.filename)
    file.file.seek(0)
    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    logger.info("Submission saved to upload: %s and temp: %s", file_path, temp_submission_dir)
    return temp_submission_dir

def extract_submission_files(temp_submission_dir: str, temp_dir: str) -> List[str]:
    """Extract JSON files from temp submission directory (handles both ZIP and JSON files)"""
    json_files = []
    
    for file_path in os.listdir(temp_submission_dir):
        full_path = os.path.join(temp_submission_dir, file_path)
        
        if file_path.lower().endswith('.json'):
            json_files.append(full_path)
        elif file_path.lower().endswith('.zip'):
            # Extract ZIP file to temp directory
            extract_dir = os.path.join(temp_dir, f"extract_{file_path.split('.')[0]}")
            os.makedirs(extract_dir, exist_ok=True)
            
            with zipfile.ZipFile(full_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Find JSON files in extracted content
            for root, _, files in os.walk(extract_dir):
                for f in files:
                    if f.lower().endswith('.json'):
                        json_files.append(os.path.join(root, f))
    
    return json_files

def process_json_file(json_file: str, solution_dir: str, exercise_type: str, graded_submission_dir: str) -> Dict:
    """Process individual JSON file and save feedback to graded submission directory"""
    safe_filename = os.path.basename(json_file)
    
    result = {
        "filename": safe_filename,
        "safe_filename": safe_filename,
        "grading": None,
        "feedback_file": None,
        "status": "failed",
        "message": None
    }

    if exercise_type != "ER":
        result.update({
            "status": "success", 
            "message": "No grading available for this exercise type"
        })
        return result

    
    solution_path = os.path.join(solution_dir, safe_filename)
    if not os.path.exists(solution_path):
        logger.warning("Solution file not found: %s", solution_path)
        result["message"] = f"Solution file {safe_filename} not found"
        return result

    try:
        with open(solution_path, 'r') as sol_file:
            solution_data = json.load(sol_file)
        logger.debug("Loaded solution file: %s", solution_path)
    except Exception as e:
        logger.error("Error loading solution file %s: %s", solution_path, str(e))
        result["message"] = f"Failed to load solution file {safe_filename}: {str(e)}"
        return result

    try:
        grading_result = evaluate(exercise_type, json_file, solution_data)
        logger.debug("Grading result for %s: %s", json_file, grading_result)
    except Exception as e:
        logger.error("Error evaluating JSON file %s: %s", json_file, str(e))
        result["message"] = f"Failed to evaluate JSON file: {str(e)}"
        return result

    # Create feedback file in the graded submission directory
    feedback_filename = f"{safe_filename.split('.')[0]}_Bewertung.xlsx"
    feedback_path = os.path.join(graded_submission_dir, feedback_filename)
    
    try:
        create_review_spreadsheet(
            grading_data=grading_result,
            f_path=feedback_path,
            filename=safe_filename,
            exercise_type=exercise_type
        )
        if os.path.exists(feedback_path) and os.path.getsize(feedback_path) > 0:
            logger.info("Feedback file created: %s, size: %d bytes", feedback_path, os.path.getsize(feedback_path))
        else:
            logger.error("Feedback file not created or empty: %s", feedback_path)
            result["message"] = f"Failed to create feedback file: {feedback_filename}"
            return result
    except Exception as e:
        logger.error("Error creating feedback file %s: %s", feedback_path, str(e))
        result["message"] = f"Failed to create feedback file: {str(e)}"
        return result
    
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
    return result

def compress_graded_subdirectories(graded_dir: str) -> List[str]:
    """Compress each subdirectory in graded directory to ZIP files"""
    zip_files = []
    
    if not os.path.exists(graded_dir):
        logger.warning("Graded directory does not exist: %s", graded_dir)
        return zip_files
    
    for item in os.listdir(graded_dir):
        item_path = os.path.join(graded_dir, item)
        if os.path.isdir(item_path):
            # Check if subdirectory contains any files
            files_to_zip = []
            for root, _, files in os.walk(item_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Include Excel files and other valid files
                    if file.endswith(('.xlsx', '.xls', '.json')) and os.path.getsize(file_path) > 0:
                        files_to_zip.append(file_path)
            
            if not files_to_zip:
                logger.warning("No valid files found in graded subdirectory: %s", item_path)
                continue
            
            # Create ZIP file for this subdirectory
            zip_filename = f"{item}_Bewertung.zip"
            zip_path = os.path.join(graded_dir, zip_filename)
            
            try:
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in files_to_zip:
                        # Use relative path within the subdirectory
                        arcname = os.path.relpath(file_path, item_path)
                        zipf.write(file_path, arcname)
                        logger.debug("Added file to ZIP: %s -> %s", file_path, arcname)
                
                # Verify ZIP file is not empty (basic ZIP header is 22 bytes)
                if os.path.exists(zip_path) and os.path.getsize(zip_path) > 22:
                    zip_files.append(zip_path)
                    logger.info("Compressed graded directory to: %s, size: %d bytes", 
                              zip_path, os.path.getsize(zip_path))
                    # Remove the original directory after successful zipping
                    shutil.rmtree(item_path)
                    logger.debug("Removed original subdirectory: %s", item_path)
                else:
                    logger.warning("Created ZIP file is empty or invalid: %s", zip_path)
                    if os.path.exists(zip_path):
                        os.remove(zip_path)
                        
            except Exception as e:
                logger.error("Error creating ZIP for directory %s: %s", item_path, str(e))
                if os.path.exists(zip_path):
                    try:
                        os.remove(zip_path)
                    except:
                        pass
                continue
    
    logger.info("Created %d ZIP files in graded directory: %s", len(zip_files), graded_dir)
    return zip_files

def create_final_graded_zip(graded_dir: str, current_user: str, exercise_type: str) -> str:
    """Create final ZIP containing all graded submissions"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_zip_name = f"graded_{current_user}_{exercise_type}_{timestamp}.zip"
    final_zip_path = os.path.join(os.path.dirname(graded_dir), final_zip_name)
    
    zip_files_added = []
    
    try:
        with zipfile.ZipFile(final_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(graded_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Include ZIP files and Excel files
                    if file.endswith(('.zip', '.xlsx', '.xls')) and os.path.getsize(file_path) > 0:
                        # Use relative path from graded_dir
                        arcname = os.path.relpath(file_path, graded_dir)
                        zipf.write(file_path, arcname)
                        zip_files_added.append(file_path)
                        logger.debug("Added file to final archive: %s -> %s", file_path, arcname)
        
        # Verify final ZIP file
        if not zip_files_added:
            logger.warning("No valid files added to final archive: %s", final_zip_path)
            if os.path.exists(final_zip_path):
                os.remove(final_zip_path)
            raise ValueError("No valid graded files to include in final archive")
        
        if not os.path.exists(final_zip_path) or os.path.getsize(final_zip_path) <= 22:
            logger.error("Final ZIP file is empty or invalid: %s", final_zip_path)
            if os.path.exists(final_zip_path):
                os.remove(final_zip_path)
            raise ValueError("Final ZIP file is empty or invalid")
        
        logger.info("Created final graded ZIP: %s with %d files, size: %d bytes", 
                   final_zip_path, len(zip_files_added), os.path.getsize(final_zip_path))
        return final_zip_path
        
    except Exception as e:
        logger.error("Error creating final ZIP archive: %s", str(e))
        if os.path.exists(final_zip_path):
            try:
                os.remove(final_zip_path)
            except:
                pass
        raise

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

    upload_dir, graded_dir, solution_dir = setup_directories(current_user, exercise_type)
    results = []
    uploaded_submissions = []
    temp_dir = tempfile.mkdtemp()

    try:
        for file in files:
            file_extension, result = validate_file(file)
            if not file_extension:
                results.append(result)
                continue

            try:
                submission_name = file.filename.split('.')[0] if '.' in file.filename else file.filename
                temp_submission_dir = save_submission_to_directory(file, submission_name, upload_dir, temp_dir)
                uploaded_submissions.append(submission_name)
                
                graded_submission_dir = os.path.join(graded_dir, submission_name)
                os.makedirs(graded_submission_dir, exist_ok=True)
                
                json_files = extract_submission_files(temp_submission_dir, temp_dir)
                
                submission_results = []
                for json_file in json_files:
                    json_result = process_json_file(json_file, solution_dir, exercise_type, graded_submission_dir)
                    submission_results.append(json_result)
                
                if not json_files:
                    no_json_result = {
                        "filename": file.filename,
                        "safe_filename": file.filename,
                        "grading": None,
                        "feedback_file": None,
                        "status": "success",
                        "message": "No JSON files found in submission"
                    }
                    submission_results.append(no_json_result)
                
                results.extend(submission_results)

            except Exception as e:
                logger.error("Error processing file %s: %s", file.filename, str(e))
                error_result = result.copy()
                error_result["message"] = f"Failed to process {file.filename}: {str(e)}"
                results.append(error_result)

        # Create graded ZIP files
        graded_zip_files = compress_graded_subdirectories(graded_dir)
        logger.info("Created %d graded ZIP files", len(graded_zip_files))
        
        final_graded_zip_filename = None
        if graded_zip_files:
            try:
                final_graded_zip_path = create_final_graded_zip(graded_dir, current_user, exercise_type)
                final_graded_zip_filename = os.path.basename(final_graded_zip_path)
                logger.info("Created final graded ZIP: %s", final_graded_zip_filename)
            except Exception as e:
                logger.error("Error creating final graded ZIP: %s", str(e))
                final_graded_zip_filename = None

        return {
            "message": "Files processed successfully",
            "user": current_user,
            "results": results,
            "uploaded_files": [file.filename for file in files],
            "uploaded_submissions": uploaded_submissions,
            "graded_files": [os.path.basename(zip_file) for zip_file in graded_zip_files],
            "available_graded_files": os.listdir(graded_dir) if os.path.exists(graded_dir) else [],
            "final_graded_zip": final_graded_zip_filename,
            "has_graded_results": len(graded_zip_files) > 0
        }

    finally:
        try:
            shutil.rmtree(temp_dir)
            logger.info("Cleaned up temporary directory: %s", temp_dir)
        except Exception as e:
            logger.warning("Error cleaning up temporary directory: %s", str(e))

@app.get("/exercises/download")
async def download_feedback(
    exercise_type: str,
    current_user: str = Depends(get_current_user)
):
    if exercise_type not in EXERCISE_TYPES:
        logger.warning("Invalid exercise type: %s", exercise_type)
        raise HTTPException(status_code=400, detail="Invalid exercise type")

    graded_dir = f"./data/{current_user}/{exercise_type}/graded"
    if not os.path.exists(graded_dir):
        logger.warning("Graded directory not found: %s for user: %s", graded_dir, current_user)
        raise HTTPException(status_code=404, detail="No feedback files available")

    # Look for both ZIP files and Excel files
    feedback_files = []
    for root, dirs, files in os.walk(graded_dir):
        for file in files:
            if file.endswith(('.zip', '.xlsx', '.xls')):
                file_path = os.path.join(root, file)
                if os.path.getsize(file_path) > 0:  # Ensure file is not empty
                    feedback_files.append(file_path)

    if not feedback_files:
        logger.warning("No feedback files found in: %s for user: %s", graded_dir, current_user)
        raise HTTPException(status_code=404, detail="No feedback files available")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"{current_user}_{exercise_type}_feedback_{timestamp}.zip"
    temp_zip_path = os.path.join(tempfile.gettempdir(), zip_filename)

    try:
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in feedback_files:
                file_name = os.path.basename(file_path)
                zipf.write(file_path, arcname=file_name)
                logger.debug("Added file to download ZIP: %s -> %s", file_path, file_name)
        
        if not os.path.exists(temp_zip_path) or os.path.getsize(temp_zip_path) <= 22:
            logger.error("Download ZIP file is empty or invalid: %s", temp_zip_path)
            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
            raise HTTPException(status_code=500, detail="Failed to create valid ZIP archive")

        logger.info("Created download ZIP: %s with %d files, size: %d bytes for user: %s", 
                   temp_zip_path, len(feedback_files), os.path.getsize(temp_zip_path), current_user)
        
        return CustomFileResponse(
            path=temp_zip_path,
            filename=zip_filename,
            media_type="application/zip"
        )
        
    except Exception as e:
        logger.error("Error creating or serving ZIP archive: %s", str(e))
        if os.path.exists(temp_zip_path):
            try:
                os.remove(temp_zip_path)
            except:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to create or serve ZIP archive: {str(e)}")

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
            for root, dirs, filenames in os.walk(graded_dir):
                for filename in filenames:
                    file_path = os.path.join(root, filename)
                    if os.path.isfile(file_path):
                        files.append({
                            "name": filename,
                            "size": os.path.getsize(file_path),
                            "path": os.path.relpath(file_path, graded_dir)
                        })
        return {"files": files}
    except Exception as e:
        logger.error(f"Error getting graded files: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving graded files")

class CustomFileResponse(StarletteFileResponse):
    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Clean up temporary file after response is sent
            if hasattr(self, 'path') and self.path and os.path.exists(self.path):
                try:
                    os.remove(self.path)
                    logger.info("Deleted temporary ZIP archive: %s", self.path)
                except Exception as e:
                    logger.warning("Error deleting temporary ZIP archive: %s", str(e))

if __name__ == '__main__':
    logger.info("Starting API server")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )