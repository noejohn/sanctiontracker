from pathlib import Path
lines=Path('sanctiontracker/urls.py').read_text().splitlines()
for idx,line in enumerate(lines,1):
    if 30<=idx<=70:
        print(f"{idx}: {line}")
