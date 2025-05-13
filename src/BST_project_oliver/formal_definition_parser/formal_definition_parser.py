"""Module for parsing formal definition exercises."""

from lark import Lark
from lark_transformer import TreeTransform

def formal_definition_parser(path:str) -> list[dict]:
    """
    Parses a .txt file for formal definitions in the format of Python List[List[Dict]].

    Args:
        path (str): File path to submission.

    Returns:
        List[dict]: A list of formal definitions. Each definition is represented as a dictionary.
    """
    grammar = r"""
    ?start: statement+

    ?statement: definition | domain | complexity | extend

    definition:  NAME "=" expr
    domain: DOM "(" NAME ")" "=" expr
    extend: GRAD "(" NAME ")" "=" expr
    complexity: COMP "(" NAME ("," NAME)+ ")" "=" expr

    ?expr: tuple_expr | set_expr | power_expr | NAME | INT

    set_expr: "{" expr ("," expr)* "}"
    tuple_expr: "(" expr ("," expr)+ ")"
    power_expr: expr "^" expr

    DOM: "dom"
    GRAD: "grad"
    COMP: "comp"
    NAME:  /[A-Za-zÄÖÜäöüß_][A-Za-zÄÖÜäöüß0-9_]*/ 
    %import common.INT
    %ignore /\s+/
    """
    parser = Lark(grammar, parser="lalr")
    transformer = TreeTransform()

    with open(path, "r", encoding="utf-8") as file:
        lines = file.readlines()
        parsed_defintions = []
        for line in lines:
            try:
                    parsed_defintions.append(transformer.transform(parser.parse(line)))
            except:
                continue
    return parsed_defintions