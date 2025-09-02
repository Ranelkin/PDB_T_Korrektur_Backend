

__author__ = 'Ranel Karimov, ranelkin@icloud.com'

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