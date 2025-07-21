import re

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

evaluate_func_dep = lambda sub, sol: len(sub & sol)

if __name__ == '__main__':
    pass