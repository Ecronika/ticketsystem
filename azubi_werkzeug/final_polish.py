"""
Final polish script.

Runs pylint and autopep8 on all python files.
"""
import glob
import os
import re
import subprocess


def get_pylint_score(filepath):
    """Run pylint and returns the score as a float."""
    if not os.path.exists(filepath):
        return 0.0

    try:
        # Run pylint
        result = subprocess.run(
            ["python", "-m", "pylint", filepath],
            capture_output=True,
            text=True,
            check=False
        )
        # Extract score using regex
        match = re.search(
            r"Your code has been rated at (-?\d+\.\d+)/10", result.stdout)
        if match:
            return float(match.group(1))
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error checking {filepath}: {e}")

    return 0.0


def run_autopep8(filepath):
    """Run autopep8 in-place."""
    try:
        # Try running as module first (more reliable)
        subprocess.run(
            ["python", "-m", "autopep8", "--in-place",
                "--aggressive", "--aggressive", filepath],
            capture_output=True,
            check=False
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error formatting {filepath}: {e}")


def main():
    """Execute main function."""
    # Get all python files in current directory + tests
    files = glob.glob("*.py") + glob.glob("tests/*.py")

    # Exclude scripts that are not part of the app logic if desired
    files = [f for f in files if f not in (
        "final_polish.py", "score_check.py")]

    print("| File | Pre-Fix Score | Post-Fix Score | Delta | Status |")
    print("| :--- | :--- | :--- | :--- | :--- |")

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
            status_code = "PERFECT"
        elif post_score >= 9.0:
            status_code = "GOOD"
        elif post_score >= 8.0:
            status_code = "OK"
        else:
            status_code = "LOW"

        print(
            f"| `{f}` | {pre_score:.2f} | {post_score:.2f} | {delta_str} | {status_code} |")


if __name__ == "__main__":
    main()
