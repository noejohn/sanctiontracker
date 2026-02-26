from pathlib import Path
lines=Path('templates/admin/servicehours_management.html').read_text().splitlines()
for idx,line in enumerate(lines,1):
    if 770<=idx<=860:
        print(f"{idx}: {line}")
