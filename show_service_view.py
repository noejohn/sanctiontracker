from pathlib import Path
lines=Path('authentication/views.py').read_text().splitlines()
for idx,line in enumerate(lines,1):
    if 820<=idx<=910:
        print(f"{idx}: {line}")
