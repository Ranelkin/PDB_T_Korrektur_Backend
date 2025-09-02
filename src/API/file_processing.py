"""Module handles every file operation in the api. 
Every non-endpoint helper method involved in file handling should be in this directory
"""

import os, zipfile, shutil
import parsers.er_parser.er_parser as er_parser

from util.evaluator import evaluate
from util.log_config import setup_logging
from util.review_spreadsheet import create_review_spreadsheet

from datetime import datetime
from fastapi import HTTPException, UploadFile
from typing import List, Dict, Tuple, Optional
from parsers.func_dep_parser.func_dep_parser import parse_key_file

__author__ = 'Ranel Karimov, ranelkin@icloud.com'

logger = setup_logging("api_file_handling")

MAX_FILE_SIZE = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {".zip"}

# Directory Management
def setup_directories(current_user: str, exercise_type: str) -> Tuple[str, str, str]:
    """Create and return directory paths for user submissions."""
    upload_dir = f"./data/{current_user}/{exercise_type}/submission"
    graded_dir = f"./data/{current_user}/{exercise_type}/graded"
    solution_dir = f"./solutions/{exercise_type}"
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(graded_dir, exist_ok=True)
    return upload_dir, graded_dir, solution_dir


# File Validation and Extraction
def validate_main_zip_file(file: UploadFile) -> None:
    """Validate uploaded ZIP file size and extension."""
    if file.size > MAX_FILE_SIZE:
        logger.warning("File too large: %s", file.filename)
        raise HTTPException(status_code=400, detail=f"File exceeds size limit of {MAX_FILE_SIZE/(1024*1024):.0f}MB")

    file_extension = f".{file.filename.split('.')[-1].lower()}" if "." in file.filename else ""
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
                f.lower().endswith(('.json', '.zip', '.txt'))  
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
    """Extract JSON or TXT files from individual submission."""
    submission_files = []
    submission_name = submission_info["name"]
    submission_path = submission_info["path"]
    submission_type = submission_info["type"]
    
    if submission_type == "directory":
        for root, _, files in os.walk(submission_path):
            for file in files:
                if file.lower().endswith(('.json', '.txt')):  # Added .txt
                    submission_files.append(os.path.join(root, file))
                elif file.lower().endswith('.zip'):
                    extract_dir = os.path.join(temp_dir, f"nested_{submission_name}_{file.split('.')[0]}")
                    os.makedirs(extract_dir, exist_ok=True)
                    try:
                        with zipfile.ZipFile(os.path.join(root, file), 'r') as zip_ref:
                            zip_ref.extractall(extract_dir)
                        for nested_root, _, nested_files in os.walk(extract_dir):
                            submission_files.extend(
                                os.path.join(nested_root, nested_file)
                                for nested_file in nested_files
                                if nested_file.lower().endswith(('.json', '.txt'))  # Added .txt
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
                submission_files.extend(
                    os.path.join(root, file)
                    for file in files
                    if file.lower().endswith(('.json', '.txt'))  # Added .txt
                )
        except Exception as e:
            logger.warning("Error extracting submission ZIP %s: %s", submission_path, str(e))
    
    logger.debug("Found %d files in submission %s", len(submission_files), submission_name)
    return submission_files


# File Processing
def find_solution_file(safe_filename: str, solution_dir: str, exercise_type: str) -> Optional[str]:
    """Find matching solution file in solution directory."""
    if exercise_type == "FUNCTIONAL":
        solution_filenames = [
            safe_filename,
            safe_filename.lower(),
            safe_filename.upper(),
            "functional.txt",
            "FUNCTIONAL.txt",
        ]
    else:
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
    
    available_solutions = [f for f in os.listdir(solution_dir) if f.endswith(('.json', '.txt'))] if os.path.exists(solution_dir) else []
    logger.warning(f"Solution file not found for {safe_filename}. Available: {available_solutions}")
    return None


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


def process_submission_file(file: str, solution_dir: str, exercise_type: str, graded_submission_dir: str) -> Dict:
    """Process individual submission file and generate feedback."""
    safe_filename = os.path.basename(file)
    result = {
        "filename": safe_filename,
        "safe_filename": safe_filename,
        "grading": None,
        "feedback_file": None,
        "status": "failed",
        "message": None
    }

    if exercise_type not in ["ER", "FUNCTIONAL"]:
        result.update({"status": "success", "message": "No grading available for this exercise type"})
        return result

    solution_path = find_solution_file(safe_filename, solution_dir, exercise_type)
    if not solution_path:
        result["message"] = f"Solution file not found. Available: {', '.join(os.listdir(solution_dir) if os.path.exists(solution_dir) else [])}"
        return result

    try:
        match exercise_type: 
            case "ER": 
                parsed_solution_data = er_parser.parse_file_ER(solution_path)
            case "FUNCTIONAL":
                parsed_solution_data = parse_key_file(solution_path)
            case _: 
                parsed_solution_data = None 
                logger.error("Undefined exercise type")
                raise ValueError
        
        logger.debug("Loaded solution data from: %s", solution_path)
        
    except Exception as e:
        logger.error("Error loading solution file %s: %s", solution_path, str(e))
        result["message"] = f"Failed to load solution file: {str(e)}"
        return result

    try:
        grading_result = evaluate(exercise_type, file, parsed_solution_data)
        logger.debug("Grading result for %s: %s", file, grading_result)
    except Exception as e:
        logger.error("Error evaluating file %s: %s", file, str(e))
        result["message"] = f"Failed to evaluate file: {str(e)}"
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



   