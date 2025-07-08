import os
import json
import zipfile
import glob
import tempfile
import secrets
import shutil
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, WebSocket, Form, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from starlette.responses import FileResponse as StarletteFileResponse
from dotenv import load_dotenv
import logging
import uvicorn
from db.DB import db
from util.log_config import setup_logging
from util.evaluator import evaluate
from util.review_spreadsheet import create_review_spreadsheet
import er_parser.er_parser

# Configuration Constants
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 10080  # One week
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = ["zip"]
EXERCISE_TYPES = ["ER", "KEYS"]

# Initialize logging and environment
logger = setup_logging("API")
load_dotenv()

# Security setup
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Pydantic models
class LoginCredentials(BaseModel):
    username: str
    password: str

# FastAPI application setup
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

# Authentication functions
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

# Directory Management
def setup_directories(current_user: str, exercise_type: str) -> Tuple[str, str, str]:
    """Create and return directory paths for user submissions."""
    upload_dir = f"./data/{current_user}/{exercise_type}/submission"
    graded_dir = f"./data/{current_user}/{exercise_type}/graded"
    solution_dir = "./solutions/"
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(graded_dir, exist_ok=True)
    return upload_dir, graded_dir, solution_dir

# File Validation and Extraction
def validate_main_zip_file(file: UploadFile) -> None:
    """Validate uploaded ZIP file size and extension."""
    if file.size > MAX_FILE_SIZE:
        logger.warning("File too large: %s", file.filename)
        raise HTTPException(status_code=400, detail=f"File exceeds size limit of {MAX_FILE_SIZE/(1024*1024):.0f}MB")

    file_extension = file.filename.split(".")[-1].lower() if "." in file.filename else ""
    if file_extension not in ALLOWED_EXTENSIONS:
        logger.warning("Invalid file format: %s", file.filename)
        raise HTTPException(status_code=400, detail="File must be a ZIP file")

def extract_main_submission_zip(file: UploadFile, temp_dir: str) -> str:
    """Extract main ZIP file containing all submissions."""
    extraction_dir = os.path.join(temp_dir, "submissions")
    os.makedirs(extraction_dir, exist_ok=True)
    
    temp_zip_path = os.path.join(temp_dir, file.filename)
    file.file.seek(0)
    with open(temp_zip_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    try:
        with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
            zip_contents = zip_ref.namelist()
            logger.info(f"ZIP contains {len(zip_contents)} entries")
            for member in zip_contents:
                if '__MACOSX' in member or member.startswith('.'):
                    continue
                zip_ref.extract(member, extraction_dir)
        logger.info("Extracted main ZIP file to: %s", extraction_dir)
        return extraction_dir
    except zipfile.BadZipFile:
        logger.error("Invalid ZIP file: %s", file.filename)
        raise HTTPException(status_code=400, detail="Invalid ZIP file format")
    except Exception as e:
        logger.error("Error extracting ZIP file %s: %s", file.filename, str(e))
        raise HTTPException(status_code=500, detail=f"Failed to extract ZIP file: {str(e)}")

def find_individual_submissions(extraction_dir: str) -> List[Dict[str, str]]:
    """Identify individual submission directories or ZIP files."""
    submissions = []
    for item in os.listdir(extraction_dir):
        if item.startswith('__MACOSX') or item.startswith('.'):
            continue
            
        item_path = os.path.join(extraction_dir, item)
        if os.path.isdir(item_path):
            has_content = any(
                f.lower().endswith(('.json', '.zip'))
                for root, _, files in os.walk(item_path)
                for f in files if not f.startswith('.')
            )
            if has_content:
                submissions.append({"name": item, "path": item_path, "type": "directory"})
                logger.debug("Found submission directory: %s", item)
        
        elif item.lower().endswith('.zip'):
            submissions.append({
                "name": item.split('.')[0],
                "path": item_path,
                "type": "zip"
            })
            logger.debug("Found submission ZIP: %s", item)
    
    logger.info("Found %d individual submissions", len(submissions))
    return submissions

def extract_submission_files(submission_info: Dict[str, str], temp_dir: str) -> List[str]:
    """Extract JSON files from individual submission."""
    json_files = []
    submission_name = submission_info["name"]
    submission_path = submission_info["path"]
    submission_type = submission_info["type"]
    
    if submission_type == "directory":
        for root, _, files in os.walk(submission_path):
            for file in files:
                if file.lower().endswith('.json'):
                    json_files.append(os.path.join(root, file))
                elif file.lower().endswith('.zip'):
                    extract_dir = os.path.join(temp_dir, f"nested_{submission_name}_{file.split('.')[0]}")
                    os.makedirs(extract_dir, exist_ok=True)
                    try:
                        with zipfile.ZipFile(os.path.join(root, file), 'r') as zip_ref:
                            zip_ref.extractall(extract_dir)
                        for nested_root, _, nested_files in os.walk(extract_dir):
                            json_files.extend(
                                os.path.join(nested_root, nested_file)
                                for nested_file in nested_files
                                if nested_file.lower().endswith('.json')
                            )
                    except Exception as e:
                        logger.warning("Error extracting nested ZIP %s: %s", file, str(e))
    
    elif submission_type == "zip":
        extract_dir = os.path.join(temp_dir, f"submission_{submission_name}")
        os.makedirs(extract_dir, exist_ok=True)
        try:
            with zipfile.ZipFile(submission_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            for root, _, files in os.walk(extract_dir):
                json_files.extend(
                    os.path.join(root, file)
                    for file in files
                    if file.lower().endswith('.json')
                )
        except Exception as e:
            logger.warning("Error extracting submission ZIP %s: %s", submission_path, str(e))
    
    logger.debug("Found %d JSON files in submission %s", len(json_files), submission_name)
    return json_files

# File Processing
def find_solution_file(safe_filename: str, solution_dir: str) -> Optional[str]:
    """Find matching solution file in solution directory."""
    solution_filenames = [
        safe_filename,
        safe_filename.lower(),
        safe_filename.upper(),
        "ER.json",
        "er.json",
        "er-diagram.json",
        "er_diagram.json",
    ]
    
    for sol_filename in solution_filenames:
        test_path = os.path.join(solution_dir, sol_filename)
        if os.path.exists(test_path):
            logger.info(f"Found solution file: {test_path}")
            return test_path
    
    available_solutions = [f for f in os.listdir(solution_dir) if f.endswith('.json')] if os.path.exists(solution_dir) else []
    logger.warning(f"Solution file not found for {safe_filename}. Available: {available_solutions}")
    return None

def process_json_file(json_file: str, solution_dir: str, exercise_type: str, graded_submission_dir: str) -> Dict:
    """Process individual JSON file and generate feedback."""
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
        result.update({"status": "success", "message": "No grading available for this exercise type"})
        return result

    solution_path = find_solution_file(safe_filename, solution_dir)
    if not solution_path:
        result["message"] = f"Solution file not found. Available: {', '.join(os.listdir(solution_dir) if os.path.exists(solution_dir) else [])}"
        return result

    try:
        with open(solution_path, 'r') as sol_file:
            solution_data = json.load(sol_file)
        parsed_solution_data = er_parser.er_parser.parse_file_ER(solution_path)
        logger.debug("Loaded solution file: %s", solution_path)
    except Exception as e:
        logger.error("Error loading solution file %s: %s", solution_path, str(e))
        result["message"] = f"Failed to load solution file: {str(e)}"
        return result

    try:
        grading_result = evaluate(exercise_type, json_file, parsed_solution_data)
        logger.debug("Grading result for %s: %s", json_file, grading_result)
    except Exception as e:
        logger.error("Error evaluating JSON file %s: %s", json_file, str(e))
        result["message"] = f"Failed to evaluate JSON file: {str(e)}"
        return result

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
            raise ValueError("Feedback file not created or empty")
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

def create_final_graded_zip(graded_dir: str, current_user: str, exercise_type: str) -> str:
    """Create ZIP file containing all graded submissions."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_zip_name = f"graded_{current_user}_{exercise_type}_{timestamp}.zip"
    final_zip_path = os.path.join(os.path.dirname(graded_dir), final_zip_name)
    
    files_added = []
    try:
        with zipfile.ZipFile(final_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(graded_dir):
                dirs[:] = [d for d in dirs if not d.startswith('__MACOSX') and not d.startswith('.')]
                for file in files:
                    if file.startswith('.') or '__MACOSX' in root:
                        continue
                    if file.endswith(('.xlsx', '.xls')) and os.path.getsize(os.path.join(root, file)) > 0:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, graded_dir)
                        zipf.write(file_path, rel_path)
                        files_added.append(file_path)
                        logger.info(f"Added to ZIP: {rel_path}")
        
        if not files_added:
            logger.warning("No valid files added to final archive: %s", final_zip_path)
            if os.path.exists(final_zip_path):
                os.remove(final_zip_path)
            raise ValueError("No valid graded files to include in final archive")
        
        logger.info("Created final graded ZIP: %s with %d files, size: %d bytes", 
                   final_zip_path, len(files_added), os.path.getsize(final_zip_path))
        return final_zip_path
    except Exception as e:
        logger.error("Error creating final ZIP archive: %s", str(e))
        if os.path.exists(final_zip_path):
            os.remove(final_zip_path)
        raise

# API Endpoints
@app.post("/login")
async def login(credentials: LoginCredentials):
    """Authenticate user and return access and refresh tokens."""
    user = db.get_user(credentials.username)
    if not user or not pwd_context.verify(credentials.password, user["password_hash"]):
        logger.warning("Login failed for user: %s", credentials.username)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(data={"sub": credentials.username})
    refresh_token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=30)
    db._execute_query(
        '''UPDATE users SET token = ?, expires_at = ? WHERE email = ?''',
        (refresh_token, expires_at.isoformat(), credentials.username)
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token
    }

@app.post("/refresh")
async def refresh_token(refresh_token: str = Form(...)):
    """Refresh access token using refresh token."""
    stored_token = db.get_refresh_token(refresh_token)
    if not stored_token or stored_token["expires"] < datetime.now():
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return {
        "access_token": create_access_token(data={"sub": stored_token["username"]}),
        "token_type": "bearer"
    }

@app.post("/register/user")
async def register_user(username: str = Form(...), password: str = Form(...), role: str = Form(...)):
    """Register a new user and create their directories."""
    try:
        userdata = {"username": username, "password": password, "role": role}
        db.register_user(userdata)
        for exercise_type in EXERCISE_TYPES:
            os.makedirs(f"./data/{username}/{exercise_type}/submission", exist_ok=True)
            os.makedirs(f"./data/{username}/{exercise_type}/graded", exist_ok=True)
        return {"message": "User registered successfully"}
    except Exception as e:
        logger.error("Error creating user directories: %s", str(e))
        raise HTTPException(status_code=500, detail="Error registering user")

@app.post("/exercises/submit")
async def submit_exercises(
    exercise_type: str = Form(...),
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
):
    """Process and grade submitted ZIP file containing multiple submissions."""
    if exercise_type not in EXERCISE_TYPES:
        logger.warning("Invalid exercise type: %s", exercise_type)
        raise HTTPException(status_code=400, detail="Invalid exercise type")
    
    if not file:
        logger.warning("No file provided by user: %s", current_user)
        raise HTTPException(status_code=400, detail="No file uploaded")

    validate_main_zip_file(file)
    upload_dir, graded_dir, solution_dir = setup_directories(current_user, exercise_type)
    results = []
    processed_submissions = []
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Clean up old graded files
        if os.path.exists(graded_dir):
            shutil.rmtree(graded_dir)
            os.makedirs(graded_dir, exist_ok=True)
        
        # Extract and save main ZIP
        extraction_dir = extract_main_submission_zip(file, temp_dir)
        original_zip_path = os.path.join(upload_dir, file.filename)
        file.file.seek(0)
        with open(original_zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info("Saved original submission ZIP: %s", original_zip_path)
        
        # Find individual submissions
        individual_submissions = find_individual_submissions(extraction_dir)
        if len(individual_submissions) == 1 and individual_submissions[0]["name"].lower() == "submission":
            submission_dir = individual_submissions[0]["path"]
            student_submissions = [
                {"name": item, "path": os.path.join(submission_dir, item), "type": "directory"}
                for item in os.listdir(submission_dir)
                if os.path.isdir(os.path.join(submission_dir, item)) and not item.startswith(('__MACOSX', '.'))
                and any(f.lower().endswith('.json') for root, _, files in os.walk(os.path.join(submission_dir, item))
                        for f in files if not f.startswith('.'))
            ]
            individual_submissions = student_submissions or individual_submissions
        
        if not individual_submissions:
            raise HTTPException(status_code=400, detail="No valid submissions found in the uploaded ZIP file")
        
        # Process each submission
        for idx, submission_info in enumerate(individual_submissions):
            submission_name = submission_info["name"]
            logger.info(f"Processing submission {idx + 1}/{len(individual_submissions)}: {submission_name}")
            
            try:
                graded_submission_dir = os.path.join(graded_dir, submission_name)
                os.makedirs(graded_submission_dir, exist_ok=True)
                
                json_files = extract_submission_files(submission_info, temp_dir)
                submission_results = []
                if json_files:
                    for json_file in json_files:
                        json_result = process_json_file(json_file, solution_dir, exercise_type, graded_submission_dir)
                        submission_results.append(json_result)
                else:
                    submission_results.append({
                        "filename": submission_name,
                        "safe_filename": submission_name,
                        "grading": None,
                        "feedback_file": None,
                        "status": "warning",
                        "message": "No JSON files found in submission"
                    })
                
                results.extend(submission_results)
                processed_submissions.append(submission_name)
            except Exception as e:
                logger.error("Error processing submission %s: %s", submission_name, str(e))
                results.append({
                    "filename": submission_name,
                    "safe_filename": submission_name,
                    "grading": None,
                    "feedback_file": None,
                    "status": "failed",
                    "message": f"Failed to process submission {submission_name}: {str(e)}"
                })
                processed_submissions.append(submission_name)

        # Create final ZIP
        final_graded_zip_filename = None
        try:
            final_graded_zip_path = create_final_graded_zip(graded_dir, current_user, exercise_type)
            final_graded_zip_filename = os.path.basename(final_graded_zip_path)
        except Exception as e:
            logger.error("Error creating final graded ZIP: %s", str(e))

        successful_submissions = len([r for r in results if r["status"] == "success"])
        return {
            "message": f"Processed {successful_submissions}/{len(processed_submissions)} submissions successfully",
            "user": current_user,
            "exercise_type": exercise_type,
            "original_file": file.filename,
            "processed_submissions": processed_submissions,
            "results": results,
            "final_graded_zip": final_graded_zip_filename,
            "has_graded_results": final_graded_zip_filename is not None,
            "summary": {
                "total_submissions": len(processed_submissions),
                "successful": successful_submissions,
                "failed": len(processed_submissions) - successful_submissions
            }
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info("Cleaned up temporary directory: %s", temp_dir)

@app.get("/exercises/download")
async def download_feedback(
    exercise_type: str,
    current_user: str = Depends(get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Download graded feedback as ZIP file."""
    if exercise_type not in EXERCISE_TYPES:
        logger.warning("Invalid exercise type: %s", exercise_type)
        raise HTTPException(status_code=400, detail="Invalid exercise type")

    graded_dir = f"./data/{current_user}/{exercise_type}/graded"
    if not os.path.exists(graded_dir):
        logger.warning("Graded directory not found: %s for user: %s", graded_dir, current_user)
        raise HTTPException(status_code=404, detail="No feedback files available")

    parent_dir = os.path.dirname(graded_dir)
    graded_zip_pattern = f"graded_{current_user}_{exercise_type}_*.zip"
    graded_zip_files = glob.glob(os.path.join(parent_dir, graded_zip_pattern))
    
    if graded_zip_files:
        latest_zip = max(graded_zip_files, key=os.path.getctime)
        zip_filename = os.path.basename(latest_zip)
        logger.info("Serving existing graded ZIP: %s for user: %s", latest_zip, current_user)
        return StarletteFileResponse(
            path=latest_zip,
            filename=zip_filename,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'}
        )
    
    feedback_files = [
        os.path.join(root, file)
        for root, _, files in os.walk(graded_dir)
        for file in files
        if file.endswith(('.xlsx', '.xls')) and os.path.getsize(os.path.join(root, file)) > 0
    ]
    
    if not feedback_files:
        logger.warning("No feedback files found in: %s for user: %s", graded_dir, current_user)
        raise HTTPException(status_code=404, detail="No feedback files available")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"{current_user}_{exercise_type}_feedback_{timestamp}.zip"
    temp_zip_path = os.path.join(tempfile.gettempdir(), zip_filename)

    try:
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in feedback_files:
                rel_path = os.path.relpath(file_path, graded_dir)
                zipf.write(file_path, arcname=rel_path)
                logger.debug("Added file to download ZIP: %s -> %s", file_path, rel_path)
        
        if not os.path.exists(temp_zip_path) or os.path.getsize(temp_zip_path) <= 22:
            logger.error("Download ZIP file is empty or invalid: %s", temp_zip_path)
            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
            raise HTTPException(status_code=500, detail="Failed to create valid ZIP archive")

        logger.info("Created download ZIP: %s with %d files, size: %d bytes for user: %s", 
                   temp_zip_path, len(feedback_files), os.path.getsize(temp_zip_path), current_user)
        
        background_tasks.add_task(lambda path: os.remove(path) if os.path.exists(path) else None, temp_zip_path)
        return StarletteFileResponse(
            path=temp_zip_path,
            filename=zip_filename,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
            background=background_tasks
        )
    except Exception as e:
        logger.error("Error creating or serving ZIP archive: %s", str(e))
        if os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)
        raise HTTPException(status_code=500, detail=f"Failed to create or serve ZIP archive: {str(e)}")

@app.websocket("/ws/depict-corrected-files")
async def depict_files(websocket: WebSocket, exercise_type: str, current_user: str = Depends(get_current_user)):
    """WebSocket endpoint to list available graded files."""
    await websocket.accept()
    try:
        import time
        time.sleep(3)  # Simulate processing delay
        graded_dir = f"./data/{current_user}/{exercise_type}/graded"
        available_files = [
            os.path.relpath(os.path.join(root, file), graded_dir)
            for root, _, files in os.walk(graded_dir)
            for file in files
            if file.endswith(('.xlsx', '.xls'))
        ]
        
        logger.info(f"Available graded files for {current_user}/{exercise_type}: {available_files}")
        await websocket.send_json({"available_files": available_files})
        await websocket.close()
    except Exception as e:
        logger.error(f"Error in depict_files websocket: {str(e)}")
        await websocket.send_json({"error": str(e)})
        await websocket.close()

@app.get("/verify-token")
async def verify_token(current_user: str = Depends(get_current_user)):
    """Verify if token is valid and return username."""
    return {"username": current_user}

@app.get("/exercises/graded")
async def get_graded_exercises(type: str, current_user: str = Depends(get_current_user)):
    """Retrieve list of graded exercise files."""
    try:
        graded_dir = f"./data/{current_user}/{type}/graded"
        files = [
            {
                "name": filename,
                "size": os.path.getsize(os.path.join(root, filename)),
                "path": os.path.relpath(os.path.join(root, filename), graded_dir)
            }
            for root, _, filenames in os.walk(graded_dir)
            for filename in filenames
            if os.path.isfile(os.path.join(root, filename))
        ]
        return {"files": files}
    except Exception as e:
        logger.error(f"Error getting graded files: %s", str(e))
        raise HTTPException(status_code=500, detail="Error retrieving graded files")

if __name__ == '__main__':
    logger.info("Starting API server")
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )