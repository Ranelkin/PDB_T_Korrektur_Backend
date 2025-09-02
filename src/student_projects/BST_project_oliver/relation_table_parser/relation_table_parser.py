"""Module for parsing relationtable exercises."""

import ast
import re

def section_splitter(block: str, marker:str, specification:str = None) -> list[str]:
    """
    Splits a block of text into sections based on a marker.
    Optionally filters sections that start with a given specification.

    Args:
        block (str): The full text content to split.
        marker (str): Delimiter to split sections (e.g. "//").
        specification (str, optional): If provided, only include sections that start with this string.

    Returns:
        List[str]: A list of relevant sections as strings.
    """
    if specification:
        section_list = [section.strip() for section in block.split(marker) if section.strip() and section.startswith(specification)]
    else:
        section_list = [section.strip() for section in block.split(marker) if section.strip()]
    return section_list


def relation_table_parser(path:str) -> list[list[dict]]:
    """
    Parses a .txt file for relation tables in the format of Python List[List[Dict]].

    Args:
        path (str): File path to submission.

    Returns:
        List[List[dict]]: A list of relation tables. Each table is represented as a list of dictionaries.
    """
    with open(path, "r", encoding="utf-8") as file:
        content = file.read()
        parsed_tables = []

        section_list = section_splitter(content, "//", "RelationTables") # only go trough //RelationTables sections 

        for section in section_list:
            table_list = section_splitter(section.lower(), "\n\n") # splitting the tables if there are more than one
            for table in table_list:
                try:
                    table = "".join(re.findall(r'\[.*?\]', table, re.DOTALL)) # get rid of characters in front of structure of interest
                    parsed_tables.append(ast.literal_eval(table))
                except:
                    continue
        return parsed_tables