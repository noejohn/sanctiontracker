from pathlib import Path
lines=Path('authentication/views.py').read_text().splitlines()
for idx,line in enumerate(lines,1):
    if 614<=idx<=750:
        print(f"{idx}: {line}")
