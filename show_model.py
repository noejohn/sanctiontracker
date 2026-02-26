from pathlib import Path
lines=Path('authentication/models.py').read_text().splitlines()
for idx,line in enumerate(lines,1):
    if 150<=idx<=260:
        print(f"{idx}: {line}")
