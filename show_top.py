from pathlib import Path
text=Path('authentication/views.py').read_text().splitlines()
for idx,line in enumerate(text,1):
    if idx<=80:
        print(f"{idx}: {line}")
