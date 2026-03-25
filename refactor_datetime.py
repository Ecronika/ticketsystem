import os

directory = r"c:\Users\tpaul\.gemini\antigravity\scratch\Ticketsystem\ticketsystem"
target = "datetime.now(timezone.utc).replace(tzinfo=None)"
replacement = "get_utc_now()"
files_changed = []

for root, _, files in os.walk(directory):
    # skip env or venv if they exist, but inside ticketsystem there aren't any
    for f in files:
        if f.endswith('.py') and f != 'utils.py':
            filepath = os.path.join(root, f)
            with open(filepath, 'r', encoding='utf-8') as file:
                content = file.read()
            
            if target in content:
                content = content.replace(target, replacement)
                if "from utils import get_utc_now" not in content:
                    content = "from utils import get_utc_now\n" + content
                with open(filepath, 'w', encoding='utf-8') as file:
                    file.write(content)
                files_changed.append(f)

print(f"Changed {len(files_changed)} files: {', '.join(files_changed)}")
