import zipfile
import xml.etree.ElementTree as ET
import os

def get_docx_text(path):
    if not os.path.exists(path):
        return f"File {path} not found"
    try:
        document = zipfile.ZipFile(path)
        xml_content = document.read('word/document.xml')
        document.close()
        tree = ET.fromstring(xml_content)
        text = ""
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        for paragraph in tree.findall('.//w:p', ns):
            p_text = ""
            for node in paragraph.findall('.//w:t', ns):
                if node.text:
                    p_text += node.text
            text += p_text + "\n"
        return text
    except Exception as e:
        return f"Error reading docx: {str(e)}"

if __name__ == "__main__":
    docx_path = r'c:\Users\Admin\Desktop\LION WEBSITE\lion_malion_security_analysis.docx'
    full_text = get_docx_text(docx_path)
    with open('security_analysis.txt', 'w', encoding='utf-8') as f:
        f.write(full_text)
    print("Extracted to security_analysis.txt")
