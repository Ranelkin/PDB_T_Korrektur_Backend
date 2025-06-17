import os, json, zipfile, glob, tempfile
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, WebSocket
from fastapi import Form
import uvicorn
from db.DB import db
from jose import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
import er_parser.er_parser
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
import er_parser
from starlette.middleware.base import BaseHTTPMiddleware

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
logger = setup_logging("API")
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 10080
MAX_FILE_SIZE = 1024 * 1024 * 50     # Increased to 50MB for single ZIP with multiple submissions
ALLOWED_EXTENSIONS = ["zip"]  # Only ZIP files allowed for main submission

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

def validate_main_zip_file(file: UploadFile) -> bool:
    """Validate the main ZIP file containing all submissions"""
    if file.size > MAX_FILE_SIZE:
        logger.warning("File too large: %s", file.filename)
        raise HTTPException(status_code=400, detail=f"File {file.filename} exceeds size limit of {MAX_FILE_SIZE/(1024*1024):.0f}MB")

    file_extension = file.filename.split(".")[-1].lower() if "." in file.filename else ""
    if file_extension not in ALLOWED_EXTENSIONS:
        logger.warning("Invalid file format: %s", file.filename)
        raise HTTPException(status_code=400, detail=f"File {file.filename} must be a ZIP file")

    return True

def extract_main_submission_zip(file: UploadFile, temp_dir: str) -> str:
    """Extract the main ZIP file and return the extraction directory"""
    extraction_dir = os.path.join(temp_dir, "submissions")
    os.makedirs(extraction_dir, exist_ok=True)
    
    # Save the uploaded ZIP file temporarily
    temp_zip_path = os.path.join(temp_dir, file.filename)
    file.file.seek(0)
    with open(temp_zip_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Extract the main ZIP file
    try:
        with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
            # Get list of files in ZIP
            zip_contents = zip_ref.namelist()
            logger.info(f"ZIP contains {len(zip_contents)} entries")
            
            # Extract only non-macOS files
            for member in zip_contents:
                # Skip macOS metadata
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
    """Find individual submission directories/ZIP files within the extracted main ZIP"""
    submissions = []
    
    # Look for directories and ZIP files in the extraction directory
    for item in os.listdir(extraction_dir):
        # Skip macOS metadata directories
        if item.startswith('__MACOSX') or item.startswith('.'):
            continue
            
        item_path = os.path.join(extraction_dir, item)
        
        if os.path.isdir(item_path):
            # Check if directory contains JSON files or ZIP files
            has_content = False
            for root, dirs, files in os.walk(item_path):
                if any(f.lower().endswith(('.json', '.zip')) for f in files if not f.startswith('.')):
                    has_content = True
                    break
            
            if has_content:
                submissions.append({
                    "name": item,
                    "path": item_path,
                    "type": "directory"
                })
                logger.debug("Found submission directory: %s", item)
        
        elif item.lower().endswith('.zip'):
            submissions.append({
                "name": item.split('.')[0],  # Remove .zip extension for name
                "path": item_path,
                "type": "zip"
            })
            logger.debug("Found submission ZIP: %s", item)
    
    logger.info("Found %d individual submissions", len(submissions))
    return submissions

def extract_submission_files(submission_info: Dict[str, str], temp_dir: str) -> List[str]:
    """Extract JSON files from individual submission (handles both directories and ZIP files)"""
    json_files = []
    submission_name = submission_info["name"]
    submission_path = submission_info["path"]
    submission_type = submission_info["type"]
    
    if submission_type == "directory":
        # Search for JSON files in the directory
        for root, dirs, files in os.walk(submission_path):
            for file in files:
                if file.lower().endswith('.json'):
                    json_files.append(os.path.join(root, file))
                elif file.lower().endswith('.zip'):
                    # Extract nested ZIP files
                    zip_path = os.path.join(root, file)
                    extract_dir = os.path.join(temp_dir, f"nested_{submission_name}_{file.split('.')[0]}")
                    os.makedirs(extract_dir, exist_ok=True)
                    
                    try:
                        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                            zip_ref.extractall(extract_dir)
                        
                        # Find JSON files in extracted nested content
                        for nested_root, _, nested_files in os.walk(extract_dir):
                            for nested_file in nested_files:
                                if nested_file.lower().endswith('.json'):
                                    json_files.append(os.path.join(nested_root, nested_file))
                    except Exception as e:
                        logger.warning("Error extracting nested ZIP %s: %s", zip_path, str(e))
    
    elif submission_type == "zip":
        # Extract the submission ZIP file
        extract_dir = os.path.join(temp_dir, f"submission_{submission_name}")
        os.makedirs(extract_dir, exist_ok=True)
        
        try:
            with zipfile.ZipFile(submission_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Find JSON files in extracted content
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    if file.lower().endswith('.json'):
                        json_files.append(os.path.join(root, file))
        except Exception as e:
            logger.warning("Error extracting submission ZIP %s: %s", submission_path, str(e))
    
    logger.debug("Found %d JSON files in submission %s", len(json_files), submission_name)
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

    # Look for solution files with common naming patterns
    solution_filenames = [
        safe_filename,  # exact match
        safe_filename.lower(),  # lowercase version
        safe_filename.upper(),  # uppercase version
        "ER.json",  # common default name
        "er.json",  # lowercase default
        "er-diagram.json",  # alternative naming
        "er_diagram.json",  # underscore version
    ]
    
    solution_path = None
    for sol_filename in solution_filenames:
        test_path = os.path.join(solution_dir, sol_filename)
        if os.path.exists(test_path):
            solution_path = test_path
            logger.info(f"Found solution file: {solution_path}")
            break
    
    if not solution_path:
        # List available solution files for debugging
        available_solutions = []
        if os.path.exists(solution_dir):
            available_solutions = [f for f in os.listdir(solution_dir) if f.endswith('.json')]
        logger.warning(f"Solution file not found for {safe_filename}. Available solutions: {available_solutions}")
        result["message"] = f"Solution file not found. Available: {', '.join(available_solutions)}"
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

def create_final_graded_zip(graded_dir: str, current_user: str, exercise_type: str) -> str:
    """Create final ZIP containing all graded submissions"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_zip_name = f"graded_{current_user}_{exercise_type}_{timestamp}.zip"
    final_zip_path = os.path.join(os.path.dirname(graded_dir), final_zip_name)
    
    files_added = []
    
    # Log the graded directory structure
    logger.info(f"Creating final ZIP from graded directory: {graded_dir}")
    logger.info("Directory structure:")
    for root, dirs, files in os.walk(graded_dir):
        # Skip macOS metadata directories
        dirs[:] = [d for d in dirs if not d.startswith('__MACOSX') and not d.startswith('.')]
        
        level = root.replace(graded_dir, '').count(os.sep)
        indent = ' ' * 2 * level
        logger.info(f"{indent}{os.path.basename(root)}/")
        subindent = ' ' * 2 * (level + 1)
        for file in files:
            if not file.startswith('.'):
                logger.info(f"{subindent}{file} ({os.path.getsize(os.path.join(root, file))} bytes)")
    
    try:
        with zipfile.ZipFile(final_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(graded_dir):
                # Skip macOS metadata directories
                dirs[:] = [d for d in dirs if not d.startswith('__MACOSX') and not d.startswith('.')]
                
                for file in files:
                    # Skip hidden files and macOS metadata
                    if file.startswith('.') or '__MACOSX' in root:
                        continue
                        
                    file_path = os.path.join(root, file)
                    # Include Excel files and other valid files
                    if file.endswith(('.xlsx', '.xls')) and os.path.getsize(file_path) > 0:
                        # Create a clean archive structure: submission_name/filename
                        rel_path = os.path.relpath(file_path, graded_dir)
                        zipf.write(file_path, rel_path)
                        files_added.append(file_path)
                        logger.info(f"Added to ZIP: {rel_path}")
        
        # Verify final ZIP file
        if not files_added:
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
                   final_zip_path, len(files_added), os.path.getsize(final_zip_path))
        
        # List contents of created ZIP for verification
        logger.info("ZIP contents:")
        with zipfile.ZipFile(final_zip_path, 'r') as zipf:
            for info in zipf.filelist:
                logger.info(f"  {info.filename} ({info.file_size} bytes)")
        
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
    file: UploadFile = File(...),  # Changed to single file
    current_user: str = Depends(get_current_user),
):
    if exercise_type not in EXERCISE_TYPES:
        logger.warning("Invalid exercise type: %s", exercise_type)
        raise HTTPException(status_code=400, detail="Invalid exercise type")
    
    if not file:
        logger.warning("No file provided by user: %s", current_user)
        raise HTTPException(status_code=400, detail="No file uploaded")

    # Validate the main ZIP file
    validate_main_zip_file(file)

    upload_dir, graded_dir, solution_dir = setup_directories(current_user, exercise_type)
    results = []
    processed_submissions = []
    temp_dir = tempfile.mkdtemp()
    
    # Clean up old graded files before processing new ones
    logger.info(f"Cleaning up old graded files in: {graded_dir}")
    if os.path.exists(graded_dir):
        for root, dirs, files in os.walk(graded_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))

    try:
        # Extract the main ZIP file containing all submissions
        extraction_dir = extract_main_submission_zip(file, temp_dir)
        
        # Save the original ZIP to upload directory for record keeping
        original_zip_path = os.path.join(upload_dir, file.filename)
        file.file.seek(0)
        with open(original_zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info("Saved original submission ZIP: %s", original_zip_path)
        
        # Find individual submissions within the extracted ZIP
        individual_submissions = find_individual_submissions(extraction_dir)
        
        # If we only found one submission called "submission", check if it contains multiple student directories
        if len(individual_submissions) == 1 and individual_submissions[0]["name"].lower() == "submission":
            logger.info("Found single 'submission' directory, checking for student subdirectories...")
            submission_dir = individual_submissions[0]["path"]
            student_submissions = []
            
            for item in os.listdir(submission_dir):
                if item.startswith('__MACOSX') or item.startswith('.'):
                    continue
                    
                item_path = os.path.join(submission_dir, item)
                if os.path.isdir(item_path):
                    # Check if directory contains JSON files
                    has_json = False
                    for root, dirs, files in os.walk(item_path):
                        if any(f.lower().endswith('.json') for f in files if not f.startswith('.')):
                            has_json = True
                            break
                    
                    if has_json:
                        student_submissions.append({
                            "name": item,
                            "path": item_path,
                            "type": "directory"
                        })
                        logger.info(f"Found student submission directory: {item}")
            
            if student_submissions:
                individual_submissions = student_submissions
                logger.info(f"Found {len(student_submissions)} student submissions inside 'submission' directory")
        
        if not individual_submissions:
            logger.warning("No valid submissions found in ZIP file")
            raise HTTPException(status_code=400, detail="No valid submissions found in the uploaded ZIP file")
        
        logger.info(f"Found {len(individual_submissions)} individual submissions to process")
        
        # Process each individual submission
        for idx, submission_info in enumerate(individual_submissions):
            submission_name = submission_info["name"]
            logger.info(f"Processing submission {idx + 1}/{len(individual_submissions)}: {submission_name}")
            
            try:
                # Create graded directory for this submission
                graded_submission_dir = os.path.join(graded_dir, submission_name)
                os.makedirs(graded_submission_dir, exist_ok=True)
                logger.info(f"Created graded submission directory: {graded_submission_dir}")
                
                # Extract JSON files from this submission
                json_files = extract_submission_files(submission_info, temp_dir)
                logger.info(f"Found {len(json_files)} JSON files in submission {submission_name}")
                
                submission_results = []
                if json_files:
                    for json_file in json_files:
                        logger.info(f"Processing JSON file: {json_file}")
                        json_result = process_json_file(json_file, solution_dir, exercise_type, graded_submission_dir)
                        submission_results.append(json_result)
                        logger.info(f"JSON file processing result: {json_result['status']} - {json_result.get('message', 'OK')}")
                else:
                    # No JSON files found, still create a result entry
                    no_json_result = {
                        "filename": submission_name,
                        "safe_filename": submission_name,
                        "grading": None,
                        "feedback_file": None,
                        "status": "warning",
                        "message": "No JSON files found in submission"
                    }
                    submission_results.append(no_json_result)
                    logger.warning(f"No JSON files found in submission: {submission_name}")
                
                results.extend(submission_results)
                processed_submissions.append(submission_name)
                
            except Exception as e:
                logger.error("Error processing submission %s: %s", submission_name, str(e))
                error_result = {
                    "filename": submission_name,
                    "safe_filename": submission_name,
                    "grading": None,
                    "feedback_file": None,
                    "status": "failed",
                    "message": f"Failed to process submission {submission_name}: {str(e)}"
                }
                results.append(error_result)
                processed_submissions.append(submission_name)

        # Create final graded ZIP file
        final_graded_zip_filename = None
        try:
            final_graded_zip_path = create_final_graded_zip(graded_dir, current_user, exercise_type)
            final_graded_zip_filename = os.path.basename(final_graded_zip_path)
            logger.info("Created final graded ZIP: %s", final_graded_zip_filename)
        except Exception as e:
            logger.error("Error creating final graded ZIP: %s", str(e))
            # Don't fail the entire request if ZIP creation fails
            final_graded_zip_filename = None

        successful_submissions = len([r for r in results if r["status"] == "success"])
        total_submissions = len(processed_submissions)
        
        logger.info(f"Processing complete: {successful_submissions}/{total_submissions} successful")

        return {
            "message": f"Processed {successful_submissions}/{total_submissions} submissions successfully",
            "user": current_user,
            "exercise_type": exercise_type,
            "original_file": file.filename,
            "processed_submissions": processed_submissions,
            "results": results,
            "final_graded_zip": final_graded_zip_filename,
            "has_graded_results": final_graded_zip_filename is not None,
            "summary": {
                "total_submissions": total_submissions,
                "successful": successful_submissions,
                "failed": total_submissions - successful_submissions
            }
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

    # Look for the most recent graded ZIP file in the parent directory
    parent_dir = os.path.dirname(graded_dir)
    graded_zip_pattern = f"graded_{current_user}_{exercise_type}_*.zip"
    graded_zip_files = glob.glob(os.path.join(parent_dir, graded_zip_pattern))
    
    if graded_zip_files:
        # Return the most recent ZIP file
        latest_zip = max(graded_zip_files, key=os.path.getctime)
        zip_filename = os.path.basename(latest_zip)
        
        logger.info("Serving existing graded ZIP: %s for user: %s", latest_zip, current_user)
        return StarletteFileResponse(
            path=latest_zip,
            filename=zip_filename,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{zip_filename}"'
            }
        )
    
    # Fallback: create ZIP from individual files if no pre-created ZIP exists
    feedback_files = []
    for root, dirs, files in os.walk(graded_dir):
        for file in files:
            if file.endswith(('.xlsx', '.xls')):
                file_path = os.path.join(root, file)
                if os.path.getsize(file_path) > 0:
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
                # Maintain directory structure in ZIP
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
        
        # Use a background task to clean up the file after sending
        from fastapi import BackgroundTasks
        background_tasks = BackgroundTasks()
        
        def cleanup_file(filepath: str):
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                    logger.info("Deleted temporary ZIP archive: %s", filepath)
            except Exception as e:
                logger.warning("Error deleting temporary ZIP archive: %s", str(e))
        
        background_tasks.add_task(cleanup_file, temp_zip_path)
        
        return StarletteFileResponse(
            path=temp_zip_path,
            filename=zip_filename,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{zip_filename}"'
            },
            background=background_tasks
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
        available_files = []
        
        if os.path.exists(graded_dir):
            for root, dirs, files in os.walk(graded_dir):
                for file in files:
                    if file.endswith(('.xlsx', '.xls')):
                        rel_path = os.path.relpath(os.path.join(root, file), graded_dir)
                        available_files.append(rel_path)
        
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

if __name__ == '__main__':
    logger.info("Starting API server")
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )