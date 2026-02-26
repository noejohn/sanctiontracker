from pathlib import Path
text=Path('templates/Student/service_hours.html').read_text().splitlines()
for idx,line in enumerate(text,1):
    if idx<=200:
        print(f"{idx}: {line}")
