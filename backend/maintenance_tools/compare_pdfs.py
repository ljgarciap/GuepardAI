import PyPDF2
import os

def extract_text(pdf_path):
    if not os.path.exists(pdf_path):
        return f"Error: {pdf_path} not found"
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            text = ""
            for i, page in enumerate(reader.pages):
                text += f"\n--- PAGE {i+1} ---\n"
                text += page.extract_text()
            return text
    except Exception as e:
        return f"Error reading {pdf_path}: {e}"

path_our = "compare_36.pdf"
path_replit = "replit.v1.Tesco-Clubcard-Advantage.pdf"

print("EXTRACTING OUR PDF (P36):")
print(extract_text(path_our))
print("\n" + "="*50 + "\n")
print("EXTRACTING REPLIT PDF:")
print(extract_text(path_replit))
