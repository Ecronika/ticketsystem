"""
Score check script.

Checks Pylint scores for core files.
"""
import subprocess
import re
import os


def main():
    """Main execution function."""
    # Files to check (explicit list to avoid checking scripts)
    files = [
        'app.py', 'routes.py', 'services.py', 'models.py',
        'extensions.py', 'forms.py', 'pdf_utils.py', 'verify_setup.py'
    ]

    print("| Datei | Pylint Score |")
    print("| :--- | :--- |")

    for f in files:
        if not os.path.exists(f):
            continue

        proc = subprocess.run(
            ["python", "-m", "pylint", f],
            capture_output=True,
            text=True,
            check=False
        )
        match = re.search(r"Your code has been rated at (-?\d+\.\d+)/10", proc.stdout)

        score = match.group(1) if match else "N/A"

        # Conditional formatting (Text based)
        status = ""
        try:
            if float(score) >= 8.0:
                status = "PASS"
            elif float(score) >= 5.0:
                status = "WARN"
            else:
                status = "FAIL"
        except ValueError:
            pass

        print(f"| `{f}` | **{score}** ({status}) |")


if __name__ == "__main__":
    main()
