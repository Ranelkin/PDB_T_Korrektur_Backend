""" Module for the parsing of the 
ER Diagramm exercise. The idea behind that is representing 
a table as a node with properties and relationships as edges. 
We traverse each and every node and look heuristically for the equivalence of the graph. 
We use the abstract syntax trees module to do so where necesarry 
"""

# Abstract syntax tree: AST 
from ..util.log_config import setup_logging
import ast
import logging
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
            if section_lower: 
                ##The first str in section is the section definition ie (tables, relations)
                if section_lower[0]=="tables":  
                    logger.info(f" Tables section: {section_lower}\n\n")
                    parsed_file["tables"] = parse_tables(section_lower)
                    debug_logger.debug(f" parsed file tables: {parsed_file["tables"]}")
                elif section_lower[0]=="relation": 
                    logger.info(f" Relation section: {section_lower}")
                    parsed_file["relations"] = parse_relations(section_lower)
                    debug_logger.debug(f" parsed file relations: {parsed_file["relations"]}")
                else:
                    logger.info(f" Undefined sections // comments are ignored")
                    logger.info(section_lower)
        
    return parsed_file

def parse_tables(section: list[str]) -> dict:
    """Parses table section in the student's submission.

    Args:
        section (list[str]): table section list with table def. from student submission

    Returns:
        dict: dictionary with parsed table definitions
    """
    tables = dict()
    debug_logger.debug(f" Passed section: {section}\n\n")
    table_list: list[str] = section[1:] #Remove section definition 
    debug_logger.debug(f" List of tables: {table_list}\n\n")
    for table in table_list:
        elem = ast.literal_eval(table)
        debug_logger.debug(f" Evaluated table element: {elem}\n\n")
        table_name: str = str(elem[0])
        debug_logger.debug(f" Extracted table name {table_name}\n\n")
        attr: tuple[str] = elem[1]
        debug_logger.debug(f" table attributes: {attr}\n\n")
        tables[table_name] = attr
    
    return tables

def parse_relations(section: list[str]) -> dict:
    """Parses relations from student submission.

    Args:
        section (str): exercise relation section

    Returns:
        dict: contains name and attr of relation
    """
    relations = dict()
    debug_logger.debug(f" Passed section {section}")
    # Split into lines and skip the header line
    section: list[str] = section[1:] # remove relation definition 
    relation_list: list[str] = [line.strip() for line in section if line.strip() and not line.strip().startswith('#') and not "//" in line]
    debug_logger.debug(f" relation list: {relation_list}")
    for relation in relation_list:
        elem = ast.literal_eval(relation.strip())
        debug_logger.debug(f" Evaluated relation: {elem}\n\n")
        relation_name: str = str(elem[0])
        debug_logger.debug(f" relation name: {relation_name}\n\n")
        attr = elem[1]
        debug_logger.debug(f" relation attributes: {attr}\n\n")
        tables = attr[0]  # Table definition
        debug_logger.debug(f" Table def: {tables}\n\n")
        rel_attr = attr[1]  # Relationship attributes
        debug_logger.debug(f" relation attributes: {rel_attr}\n\n")
        rel_dict = dict()
        rel_dict["attr"] = rel_attr
        rel_dict["tables"] = tables
        debug_logger.debug(f" parsed relations dict: {rel_dict}\n\n")
        relations[relation_name] = rel_dict
    
    return relations

if __name__ == '__main__':
    file_path = "src/er_parser/test_cases/test_case1/test1_correct.txt"
    result = parse_file_ER(file_path)
    print(result)