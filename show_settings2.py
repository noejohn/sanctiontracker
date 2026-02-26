from pathlib import Path
lines=Path('sanctiontracker/settings.py').read_text().splitlines()
for idx,line in enumerate(lines,1):
    if 110<=idx<=140:
        print(f"{idx}: {line}")
