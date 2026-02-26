from pathlib import Path
text=Path('templates/Student/service_hours.html').read_text().splitlines()
for idx,line in enumerate(text,1):
    if 200<=idx<=520:
        print(f"{idx}: {line}")
