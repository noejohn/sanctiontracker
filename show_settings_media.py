from pathlib import Path
lines=Path('sanctiontracker/settings.py').read_text().splitlines()
for idx,line in enumerate(lines,1):
    if 118<=idx<=138:
        print(f"{idx}: {line}")
