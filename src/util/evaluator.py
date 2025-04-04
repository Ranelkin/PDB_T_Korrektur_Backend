"""Module with eval methods, 
compares the solutions from the ./solutions/* dir to the students submissions
and evaluates them. 
"""

from .log_config import setup_logging
from ..er_parser import er_parser
import pandas as pd 
import copy 
from difflib import SequenceMatcher

logger = setup_logging("evaluator")
SOLUTIONS_DIR = "./solutions"

def evaluate(exercise_type: str, f_path: str, sol: dict) -> dict: 
    
    file_name = f_path.split("/")[-1]

    eval = open("./data/"+exercise_type+"/graded/"+file_name, "w")
    sol = open("./solutions/"+exercise_type, "r")
    
    match exercise_type: 
        case "ER": 
            parsed_data = er_parser.parse_file_ER(f_path, file_name)
            review = eval_ER(parsed_data, sol)
    
    return review 


def eval_ER(parsed_data: dict, sol: dict) -> dict: 

    #Available points for the exercise 
    full_points = copy.deepcopy(sol["punkte"])
    #Different object points ie. table and relations 
    achieved_points = dict()
    #Wäre wild wenn das je so passieren würde
    if parsed_data==sol: 
        return sol["punkte"]
    
    for key in sol.keys(): 
        value = parsed_data[key]
        solution  = sol[key]
        matching = SequenceMatcher(None, value, solution).ratio()
        achieved_points[key] = matching
        
    achieved_points['Gesamtpunktzahl'] = sum(achieved_points.values())
    achieved_points['Erreichbare_punktzahl'] = full_points
    return achieved_points
    
def eval_keys(parsed_data: dict) -> float: 
    pass



if __name__ == '__main__': 
    pass
