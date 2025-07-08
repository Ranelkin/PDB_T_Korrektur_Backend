import re
import os

def parse_key_file(sol, fpath):
    """
    Parse a key file and compare it with a solution.
    
    Args:
        sol: Set of solution tokens
        fpath: Path to the file to parse
        
    Returns:
        tuple: (sol, abgabe, points) where:
            - sol: The solution set (unchanged)
            - abgabe: The parsed submission as a set
            - points: Number of matching tokens between solution and submission
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
    abgabe = set(t for t in final_tokens if t)
    
    # Step 7: Map functional content between solution and submission
    points = len(sol & abgabe)
    
    return sol, abgabe, points


if __name__ == '__main__':
    # Test Case 1: Basic test with simple relations
    print("Test Case 1: Basic relations")
    test_file1 = "test1.txt"
    with open(test_file1, 'w') as f:
        f.write("k = A -> B , C -> D\nE -> F")
    
    solution1 = {"A->B", "C->D", "E->F"}
    sol, abgabe, points = parse_key_file(solution1, test_file1)
    print(f"Solution: {sol}")
    print(f"Submission: {abgabe}")
    print(f"Points: {points}")
    print(f"Expected points: 3, Actual: {points}")
    print()
    
    # Test Case 2: Test with extra spaces and formatting issues
    print("Test Case 2: Extra spaces and formatting")
    test_file2 = "test2.txt"
    with open(test_file2, 'w') as f:
        f.write("k = A  ->  B  ,  C->D  ,  E  ->  F\n  G -> H")
    
    solution2 = {"A->B", "C->D", "E->F", "G->H"}
    sol, abgabe, points = parse_key_file(solution2, test_file2)
    print(f"Solution: {sol}")
    print(f"Submission: {abgabe}")
    print(f"Points: {points}")
    print(f"Expected points: 4, Actual: {points}")
    print()
    
    # Test Case 3: Test with duplicates
    print("Test Case 3: Duplicates in submission")
    test_file3 = "test3.txt"
    with open(test_file3, 'w') as f:
        f.write("k = A->B , A->B , C->D\nA->B")
    
    solution3 = {"A->B", "C->D"}
    sol, abgabe, points = parse_key_file(solution3, test_file3)
    print(f"Solution: {sol}")
    print(f"Submission: {abgabe}")
    print(f"Points: {points}")
    print(f"Expected points: 2, Actual: {points}")
    print()
    
    # Test Case 4: Partial match
    print("Test Case 4: Partial match")
    test_file4 = "test4.txt"
    with open(test_file4, 'w') as f:
        f.write("k = A->B , X->Y , C->D")
    
    solution4 = {"A->B", "C->D", "E->F"}
    sol, abgabe, points = parse_key_file(solution4, test_file4)
    print(f"Solution: {sol}")
    print(f"Submission: {abgabe}")
    print(f"Points: {points}")
    print(f"Expected points: 2, Actual: {points}")
    print()
    
    # Test Case 5: Complex formatting with multiple lines
    print("Test Case 5: Complex multi-line input")
    test_file5 = "test5.txt"
    with open(test_file5, 'w') as f:
        f.write("k = A -> B ,\n    C -> D ,\n    E -> F\n    G -> H , I -> J")
    
    solution5 = {"A->B", "C->D", "E->F", "G->H", "I->J"}
    sol, abgabe, points = parse_key_file(solution5, test_file5)
    print(f"Solution: {sol}")
    print(f"Submission: {abgabe}")
    print(f"Points: {points}")
    print(f"Expected points: 5, Actual: {points}")
    print()
    
    # Test Case 6: Empty submission (after removing first 2 tokens)
    print("Test Case 6: Minimal input")
    test_file6 = "test6.txt"
    with open(test_file6, 'w') as f:
        f.write("k = ")
    
    solution6 = {"A->B"}
    sol, abgabe, points = parse_key_file(solution6, test_file6)
    print(f"Solution: {sol}")
    print(f"Submission: {abgabe}")
    print(f"Points: {points}")
    print(f"Expected points: 0, Actual: {points}")
    print()
    
    # Clean up test files
    for i in range(1, 7):
        test_file = f"test{i}.txt"
        if os.path.exists(test_file):
            os.remove(test_file)
    
    print("All test files cleaned up.")