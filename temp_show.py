from pathlib import Path
text=Path('templates/admin/sanction_management.html').read_text().splitlines()
for i in range(320, 360):
    print(f"{i+1}: {text[i]}")
