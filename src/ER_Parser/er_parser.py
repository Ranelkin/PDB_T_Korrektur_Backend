""" Module for the parsing of the 
ER Diagramm exercise. The idea behind that is representing 
a table as a node with properties and relationships as edges. 
We traverse each and every node and look heuristically for the equivalence of the graph. 

"""
from ..util.log_config import setup_logging

logger = setup_logging("er_parser")

def parse_file(path: str, filename: str = None) -> dict: 
    parsed_file = dict()
    
    with open(path, 'r') as file: 
        sections: list[str] =  str(file).split("\n\n") #Split the file text at line breaks 
        #Now process every section 
        for section in sections: 
            if "//tables" in section.lower(): 
                logger.info("Tables section", section) 
                parse_tables(section)
            elif  "//relation" in section.lower(): 
                logger.info("Relation section", section)
                parse_relations(section)
            else: 
                logger.info(f"Undefined sections found in {filename}")
                logger.info(section)

def parse_tables(section: str) -> dict: 
    table_list: list = section.split("\n")
    tables: tuple = map(eval, table_list)
    
def parse_relations(section: str) -> dict: 
    pass 

def _main(): 
    """Testing method for the Module, 
    if tests fail it may not be shipped / used
    """
    pass


if __name__ == '__main__': 
    _main()