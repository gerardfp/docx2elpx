import mammoth
from pathlib import Path

docx_path = Path(r"c:\Users\gerard\Desktop\doc2elpx\new\new.docx")
with open(docx_path, "rb") as docx_file:
    result = mammoth.convert_to_html(docx_file)
    print(result.value)
