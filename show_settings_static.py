from pathlib import Path
lines=Path('sanctiontracker/settings.py').read_text().splitlines()
for idx,line in enumerate(lines,1):
    if 120<=idx<=150:
        print(f"{idx}: {line}")
