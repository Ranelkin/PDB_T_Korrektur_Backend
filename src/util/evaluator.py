"""Module with eval methods, 
compares the solutions from the ./solutions/* dir to the students submissions
and evaluates them. 
"""

from util.log_config import setup_logging
from er_parser.er_parser import parse_file_ER
import copy
from fuzzywuzzy import fuzz
from .review_spreadsheet import create_review_spreadsheet
import os 

logger = setup_logging("evaluator")
SOLUTIONS_DIR = "./solutions"

def evaluate(exercise_type: str, f_path: str, sol: dict) -> dict: 
    """Passes the file to the correct evaluation method, 
       returns grading information in a dictionary.  

    Args:
        exercise_type (str): Type of exercise ('ER', 'keys', ...)
        f_path (str): File path of student submission
        sol (dict): Solution dictionary of parsed 'Musterlösung'

    Returns:
        dict: Grading information for student submission 
    """

    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Solution dictionary: {sol}")
    match exercise_type:
        case "ER":
            parsed_data = parse_file_ER(f_path)
            logger.info(f"Parsed student submission: {parsed_data}")
            review = eval_ER(parsed_data, sol)
            logger.info(f"Reviewed for the submission: {review}")
            return review
        case _:
            logger.warning("Unsupported exercise type: %s", exercise_type)
            return {"status": "unsupported", "details": "No grading available for this exercise type"}
        
def compare_dicts(student: dict, solution: dict, depth: int = 0, weight: float = 1.0) -> tuple[float, dict]:
    """Recursively compares two dictionaries, calculating a similarity score and detailed comparison.
    
    Args:
        student (dict): Student's parsed submission
        solution (dict): Solution dictionary
        depth (int): Current recursion depth
        weight (float): Weight for scoring at this level
    
    Returns:
        tuple: (total_score, detailed_comparison)
    """
    #Return full score if the submission is identical 
    if student == solution:
        return 1.0, {"status": "identical"}
    
    detailed = {}
    total_score = 0.0
    max_score = 0.0
    

    # Get all unique keys from both dictionaries
    all_keys = set(student.keys()) | set(solution.keys())
    
    for key in all_keys:
        detailed[key] = {}
        
        # Missing key penalty
        if key not in student:
            detailed[key]['status'] = 'missing'
            detailed[key]['score'] = 0.0
            max_score += weight
            continue
        if key not in solution:
            detailed[key]['status'] = 'extra'
            detailed[key]['score'] = 0.0
            continue
            
        student_val = student[key]
        sol_val = solution[key]
        
        # Handle different value types
        if isinstance(student_val, dict) and isinstance(sol_val, dict):
            # Recursive comparison for nested dictionaries
            sub_score, sub_detailed = compare_dicts(student_val, sol_val, depth + 1, weight / len(all_keys))
            detailed[key]['status'] = 'nested'
            detailed[key]['score'] = sub_score
            detailed[key]['details'] = sub_detailed
            total_score += sub_score * weight / len(all_keys)
            max_score += weight / len(all_keys)
            
        elif isinstance(student_val, (set, list)) and isinstance(sol_val, (set, list)):
            # Compare sets or lists
            student_set = set(student_val)
            sol_set = set(sol_val)
            
            # Calculate similarity for each element
            element_scores = []
            elements = {}
            for item in student_set | sol_set:
                if item in student_set and item in sol_set:
                    element_scores.append(1.0)
                    elements[item] = 1.0
                elif item in student_set:
                    best_score = max([fuzz.ratio(item, sol_item) / 100.0 for sol_item in sol_set] + [0.0])
                    element_scores.append(best_score)
                    elements[item] = best_score
                else:
                    element_scores.append(0.0)
                    elements[item] = 0.0
            
            # Handle empty sets
            collection_score = 1.0 if student_set == sol_set else sum(element_scores) / max(len(sol_set), 1)
            detailed[key]['status'] = 'collection'
            detailed[key]['score'] = collection_score
            detailed[key]['elements'] = elements
            total_score += collection_score * weight / len(all_keys)
            max_score += weight / len(all_keys)
            
        else:
            # Direct comparison for strings or other types
            if isinstance(student_val, str) and isinstance(sol_val, str):
                similarity = fuzz.ratio(student_val.lower(), sol_val.lower()) / 100.0
            else:
                similarity = 1.0 if student_val == sol_val else 0.0
                
            detailed[key]['status'] = 'value'
            detailed[key]['score'] = similarity
            detailed[key]['student_value'] = student_val
            detailed[key]['solution_value'] = sol_val
            total_score += similarity * weight / len(all_keys)
            max_score += weight / len(all_keys)
    
    logger.info(f"compare_dicts: total_score={total_score}, max_score={max_score}, depth={depth}")
    final_score = total_score / max_score if max_score > 0 else 1.0
    return final_score, detailed

def eval_ER(parsed_data: dict, sol: dict) -> dict: 
    """Evaluation method for students submission parsed data. 
       Returns evaluated grading 
        
    Args:
        parsed_data (dict): Parsed student submission data
        sol (dict): 'Musterlösung' dictionary to compare the student submission with  

    Returns:
        dict: Grading of student 
    """
    full_points = copy.deepcopy(sol.get("punkte", 100.0))
    logger.info(f"Received Graph for eval: {parsed_data}")
    total_score, detailed_comparison = compare_dicts(parsed_data, sol)
    achieved_points = {
        'Gesamtpunktzahl': total_score * full_points,
        'Erreichbare_punktzahl': full_points,
        'details': detailed_comparison
    }
    logger.info(f"eval_ER: total_score={total_score}, Gesamtpunktzahl={achieved_points['Gesamtpunktzahl']}")
    return achieved_points


if __name__ == '__main__':
    # Print working directory for debugging
    logger.info(f"Current working directory: {os.getcwd()}")
    # Parse the solution file
    sol = parse_file_ER(path="./solutions/ER.json")
    logger.info(f"Solution dictionary: {sol}")
    # Parse and evaluate the student submission
    submission_path = "/Users/ranelkarimov/PDB_T_Korrektur_Backend/data/test/ER/submission/ER.json"
    result = evaluate('ER', f_path=submission_path, sol=sol)
    # Create output directory
    output_dir = os.path.dirname(submission_path)
    os.makedirs(output_dir, exist_ok=True)
    # Generate the spreadsheet
    create_review_spreadsheet(
        grading_data=result,
        f_path=submission_path,
        filename="ER.json",
        exercise_type="ER"
    )