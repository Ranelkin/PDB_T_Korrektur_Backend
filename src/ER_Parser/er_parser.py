""" Module for the parsing of the 
ER Diagramm exercise. The submission is handed in in json format 
"""

# Abstract syntax tree: AST 
from ..util.log_config import setup_logging
import logging
import json
logging.basicConfig(level=logging.DEBUG)
logger = setup_logging("er_parser")
debug_logger = logging.getLogger("er_parser_debug")
debug_logger.setLevel(logging.DEBUG)

def parse_file_ER(path: str, filename: str = None) -> dict:
    """Parses student submission.

    Args:
        path (str): filepath
        filename (str, optional): Filename. Defaults to None.

    Returns:
        dict: parsed student content
    """
    parsed_file = dict()
    with open(path, 'r') as file:
        content = file.read()
        debug_logger.debug(f" File content: {content} \n\n")
        
        # Split in sections, prepare for parsing
        sections: list[str] = list(map(lambda x: x.lower(), content.split("//"))) # Split in sections 
        sections: list[list[str]] = [[s.strip() for s in l.split("\n") if s.strip()] for l in sections] # split in lines, strip whitespaces 
        debug_logger.debug(f"  sections pre parsing: {sections}\n\n")
        
        # Process each section
        for section in sections:
            # Normalize section text for case-insensitive comparison
            section_lower: list[str] = list(map(lambda x: x.lower(), section)) # Normalize to lowercase 
            section_lower: list[str] = list(filter(lambda x: x[0] != '#', section_lower)) # Filter out comment lines 
            
            debug_logger.debug(f" section after making strings lowercase and removing comments: {section_lower}\n\n")
            
    return parsed_file



if __name__ == '__main__':
    file_path = "src/er_parser/test_cases/test_case1/test1_correct.txt"
    result = parse_file_ER(file_path)
    print(result)