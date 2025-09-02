"""Module for parsing functional dependency base exercises."""

def functional_dependencies_parser(path:str) -> list[set[tuple[frozenset]]]:
    """
    Parses a .txt file for frunctional dependency bases in the format of Python List[Set[Tuple[Frozenset]]].

    Args:
        path (str): File path to submission.

    Returns:
        List[Set[Tuple[Frizenset]]]: A list of functional dependency bases. Each base is represented as a Set[Tuple[Frozenset]].
    """

    with open(path, "r", encoding="utf-8") as file:
        lines = file.readlines()
        parsed_dependencies = []

        for line in lines:
            if "f'''" in line.lower().replace(" ", ""): # search for basis
                dependency_set = set()
                for dep in line.lower().strip().replace(" ", "").replace("{", "").replace("}", "").split("=")[1].split(","): # prepare string to be parsed
                    attr_left, attr_right = dep.split("->")
                    dependency_set.add((frozenset(attr_left), frozenset(attr_right)))
            else:
                continue
            parsed_dependencies.append(dependency_set)
        return parsed_dependencies
