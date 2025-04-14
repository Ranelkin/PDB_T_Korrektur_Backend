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
    parsed_graph = dict()
    with open(path, 'r') as file:
        content = json.load(file)
        nodes = content["nodes"]
        edges = content["edges"]
        
        #Map node ID's to the node names 
        node_ids: list= [node["id"] for node in nodes] #Filter out node ids, scrap the positions 
        logger.info(f"node id's: {node_ids} \n\n")
        
        
        for edge in edges: 
            #json edge element contents 
            edge_id: str = edge["id"]
            source: str = edge["source"] # source ID
            target: str  = edge["target"] # target ID 
            
            #prepare node names 
            edge_nodes = edge_id.split(" ")[1].split("->")
            edge_node_source = edge_nodes[0]
            edge_node_target = edge_nodes[1]
            
            #create / adjust source entry
            if parsed_graph.get(edge_node_source): parsed_graph[edge_node_source]["edges"].add(edge_node_target)
            else: 
                parsed_graph[edge_node_source] = {"id": source, "edges": set()}
                parsed_graph[edge_node_source]["edges"].add(edge_node_target)
                
            #create / adjust target entry 
            if not parsed_graph.get(edge_node_target): parsed_graph[edge_node_target] = {"id": target, "edges": set()}
    
    return parsed_graph
       
        



if __name__ == '__main__':
    file_path = "src/er_parser/test_cases/aggregation.json"
    result = parse_file_ER(file_path)
    print(result)