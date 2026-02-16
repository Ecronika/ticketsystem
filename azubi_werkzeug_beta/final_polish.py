import subprocess
import re
import glob
import os

# Get all python files in current directory + tests
files = glob.glob("*.py") + glob.glob("tests/*.py")

# Exclude scripts that are not part of the app logic if desired, 
# but user said "every Python file". We might exclude this script itself.
files = [f for f in files if f != "final_polish.py" and f != "score_check.py"]

print(f"| File | Pre-Fix Score | Post-Fix Score | Delta | Status |")
print(f"| :--- | :--- | :--- | :--- | :--- |")

def get_pylint_score(filepath):
    """Runs pylint and returns the score as a float."""
    if not os.path.exists(filepath):
        return 0.0
        
    try:
        # Run pylint
        result = subprocess.run(
            ["python", "-m", "pylint", filepath], 
            capture_output=True, 
            text=True
        )
        # Extract score using regex
        match = re.search(r"Your code has been rated at (-?\d+\.\d+)/10", result.stdout)
        if match:
            return float(match.group(1))
    except Exception as e:
        print(f"Error checking {filepath}: {e}")
    
    return 0.0

def run_autopep8(filepath):
    """Runs autopep8 in-place."""
    try:
        # Try running as module first (more reliable)
        subprocess.run(
            ["python", "-m", "autopep8", "--in-place", "--aggressive", "--aggressive", filepath],
            capture_output=True
        )
    except Exception as e:
        print(f"Error formatting {filepath}: {e}")

for f in files:
    # 1. Pre-Fix Score
    pre_score = get_pylint_score(f)
    
    # 2. Auto-Format
    run_autopep8(f)
    
    # 3. Post-Fix Score
    post_score = get_pylint_score(f)
    
    # 4. Reporting
    delta = post_score - pre_score
    delta_str = f"+{delta:.2f}" if delta > 0 else f"{delta:.2f}"
    
    if post_score >= 9.5:
        status = "PERFECT"
    elif post_score >= 9.0:
        status = "GOOD"
    elif post_score >= 8.0:
        status = "OK"
    else:
        status = "LOW"
        
    print(f"| `{f}` | {pre_score:.2f} | {post_score:.2f} | {delta_str} | {status} |")
