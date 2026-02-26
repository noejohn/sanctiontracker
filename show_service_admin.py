from pathlib import Path
text=Path('templates/admin/servicehours_management.html').read_text().splitlines()
for idx,line in enumerate(text,1):
    if 300<=idx<=520:
        print(f"{idx}: {line}")
