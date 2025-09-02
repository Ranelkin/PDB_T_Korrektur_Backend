from common import compare_dicts
import copy 
from util.log_config import setup_logging

logger = setup_logging("evaluators_ER")


__author__ = 'Ranel Karimov, ranelkin@icloud.com'

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
