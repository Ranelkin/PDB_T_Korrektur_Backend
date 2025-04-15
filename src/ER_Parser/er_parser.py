""" Module for the parsing of the 
ER Diagramm exercise. The submission is handed in in json format 
"""

 
from ..util.log_config import setup_logging
import logging
import json
logging.basicConfig(level=logging.DEBUG)
logger = setup_logging("er_parser")
debug_logger = logging.getLogger("er_parser_debug")
debug_logger.setLevel(logging.DEBUG)


def parse_file_ER(path: str) -> dict:
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
        num_ids : int= len(nodes) #Filter out node ids, scrap the positions 
        logger.info(f"node id's: {num_ids} \n\n")
        
        
        for edge in edges: 
            #json edge element contents 
            edge_id: str = edge["id"]
            
            edge_list = edge_id.split(" ")
            
            #prepare node names 
            if "entity-attr" in edge_id: 
                edge_nodes = edge_list[1].split("->")
                edge_node_source = edge_nodes[0]
                edge_node_target = edge_nodes[1] #The target is the attribute 
               
                #Create adjust source entry 
                if parsed_graph.get(edge_node_source): parsed_graph[edge_node_source]["attr"].add(edge_node_target)
                else: 
                    parsed_graph[edge_node_source] = {"edges": set(), "attr": set()}
                    parsed_graph[edge_node_source]["attr"].add(edge_node_target)
                
        
            elif "isA: entity:" in edge_id: 
                edge_nodes = edge_list[2:]
                edge_node_source = edge_nodes[0].split("|")[0]
                edge_node_target = edge_nodes[1]
                
                #Create adjust source entry 
                if parsed_graph.get(edge_node_source): parsed_graph[edge_node_source]["edges"].add(edge_node_target)
                else: 
                    parsed_graph[edge_node_source] = {"edges": set(), "attr": set()}
                    parsed_graph[edge_node_source]["edges"].add(edge_node_target)
                
                #Create/ adjust target entry 
                if not parsed_graph.get(edge_node_target): parsed_graph[edge_node_target] = {"edges": set(), "attr": set()}
        
            elif "relationship-part:" in edge_id: 
                edge_nodes = edge_list[1]
                edge_attr = edge_nodes.split("$")
                relation = edge_attr[0]
                edge_attr = edge_attr[-1].split("->")
                
                edge_node_source = edge_attr[0]
                edge_node_target = edge_attr[1]
                
                # Initialize relation if it doesn't exist
                if not parsed_graph.get(relation): 
                    parsed_graph[relation] = {"edges": set(), "attr": set()}
                
                # Add edges to the relation
                parsed_graph[relation]["edges"].add(edge_node_target)
                parsed_graph[relation]["edges"].add(edge_node_source)
                
                # Initialize source and target if they don't exist
                if not parsed_graph.get(edge_node_source): 
                    parsed_graph[edge_node_source] = {"edges": set(), "attr": set()}
                if not parsed_graph.get(edge_node_target): 
                    parsed_graph[edge_node_target] = {"edges": set(), "attr": set()}
                
            elif "relationship-attr"  in edge_id: 
                edge_nodes = edge_list[1]
                edge_attr = edge_nodes.split("$")
                relation = edge_attr[0]
                
                edge_attr = edge_attr[-1].split("->")
                
                edge_node_source = edge_attr[0]
                edge_node_target = edge_attr[1]
                
                # Initialize relation if it doesn't exist
                if not parsed_graph.get(relation): 
                    parsed_graph[relation] = {"edges": set(), "attr": set()}
                
                # Add edges to the relation
                parsed_graph[relation]["edges"].add(edge_node_target)
                parsed_graph[relation]["edges"].add(edge_node_source)
                
                # Initialize source and target if they don't exist
                if not parsed_graph.get(edge_node_source): 
                    parsed_graph[edge_node_source] = {"edges": set(), "attr": set()}
                if not parsed_graph.get(edge_node_target): 
                    parsed_graph[edge_node_target] = {"edges": set(), "attr": set()}
             
            else: 
                logger.info(f"Found non branched edge: {edge}")
                continue 
                
    return parsed_graph
       
        



if __name__ == '__main__':
    file_path = "src/er_parser/test_cases/company.json"
    result = parse_file_ER(file_path)
    for res in result: 
        print(res, end=" ")
        print(result[res], end="\n")