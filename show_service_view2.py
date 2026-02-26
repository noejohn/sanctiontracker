from pathlib import Path
lines=Path('authentication/views.py').read_text().splitlines()
for idx,line in enumerate(lines,1):
    if 910<=idx<=1010:
        print(f"{idx}: {line}")
