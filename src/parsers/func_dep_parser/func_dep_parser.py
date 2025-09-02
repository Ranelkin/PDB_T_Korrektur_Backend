import re

__author__ = 'Ranel Karimov, ranelkin@icloud.com'

def parse_key_file(fpath: str):
    """
    Parse a key file and return set of parsed functional dependencies.
    
    Args:
        
        fpath: Path to the file to parse
        
    Returns:
        parsed_func_dep: parsed functional dependencies from file  
    """
    # Read the file
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Step 1: Remove line breaks
    content = content.replace('\n', ' ')
    
    # Step 2: Normalize - remove excessive spaces
    content = re.sub(' +', ' ', content)
    
    # Step 3: Group relations
    content = re.sub(r'\s*->\s*', '->', content)
    content = content.replace(" ,", ",")
    content = content.replace(", ", ",")
    
    # Step 4: Convert to tokens by splitting on spaces first
    tokens = content.split(' ')
    
    # Step 5: Remove irrelevant tokens ("k" and "=") - take tokens from index 2 onwards
    tokens = tokens[2:]
    
    # Step 5.5: Split each token by commas to separate individual relations
    final_tokens = []
    for token in tokens:
        if token:  # Skip empty tokens
            # Split by comma and add individual relations
            final_tokens.extend(token.split(','))
    
    # Step 6: Remove redundancies by converting to set and filter out empty strings
    parsed_func_dep = set(t for t in final_tokens if t)
    
    return parsed_func_dep

def evaluate_func_dep(sub, sol):
    """
    Evaluate functional dependencies by comparing submission with solution.
    Returns a dictionary compatible with create_review_spreadsheet.
    
    Args:
        sub: Set of functional dependencies from student submission
        sol: Dictionary containing solution data (or set if using old format)
        
    Returns:
        dict: Grading information in the expected format
    """
    # Handle both dictionary format (with 'punkte' key) and simple set format
    if isinstance(sol, dict):
        solution_deps = sol.get('dependencies', set())
        full_points = sol.get('punkte', 100.0)
    else:
        # Backward compatibility: if sol is just a set
        solution_deps = sol
        full_points = 100.0
    
    # Find matches, missing, and extra dependencies
    correct_deps = sub & solution_deps
    extra_deps = sub - solution_deps
    
    # Calculate score
    if len(solution_deps) > 0:
        score = len(correct_deps) / len(solution_deps)
    else:
        score = 1.0 if len(sub) == 0 else 0.0
    
    achieved_points = score * full_points
    
    # Build detailed comparison for spreadsheet
    details = {
        'functional_dependencies': {
            'status': 'collection',
            'score': score,
            'details': {
                'dependencies': {
                    'status': 'collection',
                    'score': score,
                    'elements': {}
                }
            }
        }
    }
    
    # Add all dependencies to elements with their scores
    for dep in solution_deps:
        if dep in correct_deps:
            details['functional_dependencies']['details']['dependencies']['elements'][dep] = 1.0
        else:
            details['functional_dependencies']['details']['dependencies']['elements'][dep] = 0.0
    
    # Add extra dependencies with 0 score
    for dep in extra_deps:
        details['functional_dependencies']['details']['dependencies']['elements'][f"{dep} (extra)"] = 0.0
    
    return {
        'Gesamtpunktzahl': achieved_points,
        'Erreichbare_punktzahl': full_points,
        'details': details
    }
    
if __name__ == '__main__':
    pass