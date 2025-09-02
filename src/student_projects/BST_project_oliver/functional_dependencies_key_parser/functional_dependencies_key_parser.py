"""Module for parsing functional dependency key exercises."""
import ast

def functional_dependencies_key_parser(path:str) -> list[set]:
    """
    Parses a .txt file for frunctional dependency key sets in the format of Python List[Set].

    Args:
        path (str): File path to submission.

    Returns:
        List[Set]: A list of functional dependency key sets. Each key set is represented as a Set.
    """
    with open(path, "r", encoding="utf-8") as file:
        lines = file.readlines()
        parsed_keys = []

        for line in lines:
            if "k" in line: 
                try:
                    parsed_keys.append(ast.literal_eval(line.lower().strip().replace(" ", "").split(":=")[1])) # prepare string before transforming
                except:
                    continue
        return parsed_keys
