from pathlib import Path
text = Path('templates/admin/student_management.html').read_text().splitlines()
start = next(i for i,line in enumerate(text) if '<style>' in line)
end = next(i for i,line in enumerate(text) if '</style>' in line)
for line in text[start+1:end]:
    print(line)
