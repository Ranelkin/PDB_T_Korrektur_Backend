import os
import json
import zipfile
import glob
import tempfile
import secrets
import shutil
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, UploadFile, Form, Depends, WebSocket, BackgroundTasks, File
from fastapi.responses import FileResponse as StarletteFileResponse
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel
from dotenv import load_dotenv

from db.DB import db
from util.log_config import setup_logging
import parser.er_parser.er_parser as er_parser

from API.api_config import (create_access_token, 
                      get_current_user, 
                      pwd_context )
from API.file_processing import (
                      validate_main_zip_file, 
                      setup_directories, 
                      extract_main_submission_zip, 
                      find_individual_submissions, 
                      extract_submission_files, 
                      process_submission_file, 
                      create_final_graded_zip
)

__author__ = 'Ranel Karimov, ranelkin@icloud.com'

# Initialize logging and environment
logger = setup_logging("API")
load_dotenv()

EXERCISE_TYPES = ["ER", "KEYS", "FUNCTIONAL"]  # Added FUNCTIONAL

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
    except Exception as e:
        logger.error("Error creating user directories: %s", str(e))
        raise HTTPException(status_code=500, detail="Error registering user")
    return {"message": "User registered successfully"}

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
                and any(f.lower().endswith(('.json', '.txt')) for root, _, files in os.walk(os.path.join(submission_dir, item))
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
                
                submission_files = extract_submission_files(submission_info, temp_dir)
                submission_results = []
                if submission_files:
                    for sub_file in submission_files:
                        json_result = process_submission_file(sub_file, solution_dir, exercise_type, graded_submission_dir)
                        submission_results.append(json_result)
                else:
                    submission_results.append({
                        "filename": submission_name,
                        "safe_filename": submission_name,
                        "grading": None,
                        "feedback_file": None,
                        "status": "warning",
                        "message": "No submission files found in submission"
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

        logger.info("Created download ZIP: %s with %d files, size: %d bytes", 
                   temp_zip_path, len(feedback_files), os.path.getsize(temp_zip_path))
        
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
        time.sleep(3)
        graded_dir = f"./data/{current_user}/{exercise_type}/graded"
        available_files = [
            os.path.relpath(os.path.join(root, file), graded_dir)
            for root, _, files in os.walk(graded_dir)
            for file in files
            if file.endswith(('.xlsx', '.xls'))
        ]
        
        logger.info(f"Available graded files for {current_user}/{exercise_type}: {available_files}")
        await websocket.send_json({"available_files": available_files})
    except Exception as e:
        logger.error(f"Error in downloading ZIP file: {str(e)}")
        await websocket.send_json({"error": str(e)})
    finally:
        await websocket.close()

@app.get("/verify-token")
async def verify_token(current_user: str = Depends(get_current_user)):
    """Verify if token is valid and return username."""
    return {"username": current_user}

@app.get("/exercises/graded")
async def get_graded_exercises(type: str, current_user: str = Depends(get_current_user)):
    """Retrieve list of graded files."""
    try:
        graded_dir = f"./data/{current_user}/{type}/graded"
        files = []
        if os.path.exists(graded_dir):
            for root, _, filenames in os.walk(graded_dir):
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

if __name__ == "__main__":
    logger.info("Starting API server")
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
