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
    tables: dict = dict()
    #Seperated the table definitions in 
    #a seperate list of table definitions
    table_list: list[str] = section.split("\n")
    #Process every table
    for table in table_list: 
        #Remove whitespaces
        table: str = table.replace(" ", "")
        #Split into each attribute of table def
        attr: list[str] = table.split(",")
        #The first and last element have a [ and a ] in the string element
        #Remove it. The first element is the table name
        tables[attr[0].replace("[", "")] = None #table name defined in dict 
        #Prepare attr of table
        
        
        
def parse_relations(section: str) -> dict: 
    pass 

def _main(): 
    """Testing method for the Module, 
    if tests fail it may not be shipped / used
    """
    pass


if __name__ == '__main__': 
    _main()