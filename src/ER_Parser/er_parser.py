""" Module for the parsing of the 
ER Diagramm exercise. The idea behind that is representing 
a table as a node with properties and relationships as edges. 
We traverse each and every node and look heuristically for the equivalence of the graph. 
We use the abstract syntax trees module to do so where necesarry 
"""

# Abstract syntax tree: AST 
from ..util.log_config import setup_logging
import ast 

logger = setup_logging("er_parser")

def parse_file(path: str, filename: str = None) -> dict: 
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
        sections: list[str] =  str(content).split("\n\n") #Split the file text at line breaks 
        #Now process every section 
        for section in sections: 
            if not section: 
                continue 
            if "//tables" in section.lower(): 
                logger.info("Tables section", section) 
                parsed_file["tables"] = parse_tables(section)
            elif  "//relation" in section.lower(): 
                logger.info("Relation section", section)
                parsed_file["relations"] = parse_relations(section)
            else: 
                logger.info(f"Undefined sections found in {filename}")
                logger.info(section)
    
    return parsed_file

def parse_tables(section: str) -> dict: 
    """parses table section in the students
    submission 

    Args:
        section (str): table section str from student submission 

    Returns:
        dict: dictionary with parsed table definition of student 
    """
    tables: dict = dict()
    #Seperated the table definitions in 
    #a seperate list of table definitions
    #each line has a different table definitions
    table_list: list[str] = section.split("\n")[1:]
    #Process every table
    for table in table_list: 
        if not table: 
            continue
        elem = ast.literal_eval(table.strip())
        #Table attr 
        table: str = str(elem[0])
        attr: tuple[str] = elem[1]
        #Create dict entry with table and all its declared attr 
        tables[table] = attr
    
    return tables 
        
def parse_relations(section: str) -> dict: 
    """parses relations from student submission 

    Args:
        section (str): exercise relation section

    Returns:
        dict: contains name and attr of relation 
    """
    relations = dict()
    #Seperated the relation definitions in 
    #a seperate list of relation definitions
    #each line has a different relation definition
    relation_list: list[str] = section.split("\n")[1:]
    #Process every relation
    for relation in relation_list:
        if not relation: 
            continue
        #Create AST 
        elem = ast.literal_eval(relation.strip())
        relation_name: str = str(elem[0])   #relation name 
        attr = elem[1]
        #The attr looks asf: (([table, int, int]...), (rel_attr))
        tables = attr[0] #Table definition 
        rel_attr = attr[1] #Relationship attributes 
        rel_dict = dict()
        rel_dict["attr"] = rel_attr #describes the attr the rel have 
        rel_dict["tables"] = tables # describes the rel the tables have
        relations[relation_name] = rel_dict
        
    return relations


def _main(): 
    """Testing method for the Module, 
    if tests fail it may not be shipped / used
    """
    pass


if __name__ == '__main__': 
    _main()