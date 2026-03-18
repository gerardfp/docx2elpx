import zipfile
import re
from xml.dom import minidom

def get_image_dimensions(docx_path):
    dims = []
    try:
        with zipfile.ZipFile(docx_path, 'r') as docx:
            # document.xml contains the layout
            doc_xml = docx.read('word/document.xml').decode('utf-8')
            # Look for <wp:extent cx="123" cy="456" />
            # EMUs: 1 inch = 914,400 EMUs; 1 pixel (96dpi) = 9,525 EMUs
            extents = re.findall(r'<wp:extent\s+cx="(\d+)"\s+cy="(\d+)"', doc_xml)
            for cx, cy in extents:
                width_px = int(cx) / 9525
                height_px = int(cy) / 9525
                dims.append((width_px, height_px))
    except Exception as e:
        print(f"Error: {e}")
    return dims

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python debug_xml.py <docx_path>")
        sys.exit(1)
    
    res = get_image_dimensions(sys.argv[1])
    for i, (w, h) in enumerate(res, 1):
        print(f"Image {i}: {w:.2f}px x {h:.2f}px")
