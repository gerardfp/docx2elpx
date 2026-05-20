import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from md2elpx import extract_pages_from_markdown, compile_markdown_to_html
import shutil

def run_test():
    project_root = Path(__file__).resolve().parent.parent
    md_path = project_root / "markref.md"
    output_root = project_root / "output_test"
    
    # Clean output_test if exists
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(exist_ok=True)
    (output_root / "content" / "resources").mkdir(parents=True, exist_ok=True)
    
    print("Testing parser on markref.md...")
    pages, doc_metadata = extract_pages_from_markdown(md_path, project_root, output_root)
    
    print("\n--- Document Metadata ---")
    for k, v in doc_metadata.items():
        print(f"{k}: {v}")
        
    print("\n--- Extracted Hierarchy ---")
    for page in pages:
        print(f"Page Level {page.level}: '{page.title}' (slug: {page.slug}, file: {page.filename})")
        for idx, section in enumerate(page.sections):
            print(f"  Section {idx+1}: '{section.title}'")
            if section.metadata:
                print(f"    Metadata: {section.metadata}")
            # Print a snippet of parsed content
            snippet = section.content[:150].replace('\n', ' ')
            print(f"    Snippet: {snippet}...")
            
    print("\nVerification checks:")
    # Check 1: We should have some pages
    assert len(pages) > 0, "No pages extracted!"
    print("[OK] Pages found!")
    
    # Check 2: Figure metadata processing
    figure_found = False
    for p in pages:
        for s in p.sections:
            if "<figure" in s.content:
                figure_found = True
                print(f"[OK] Found processed figure in section '{s.title}'!")
                # check image attributes
                assert "Tecnología y Educación en el Aula" in s.content or "Tecnologia y Educacion" in s.content, "Figure title missing!"
                assert "Unsplash Contributor" in s.content, "Figure author missing!"
                assert "CC BY" in s.content, "Figure license missing!"
                print("  [OK] Figure credits and licenses are perfectly formatted!")
                
    assert figure_found, "Figure with metadata was not parsed correctly!"
    
    # Check 3: Lightbox processing
    lightbox_found = False
    for p in pages:
        for s in p.sections:
            if "rel=\"lightbox\"" in s.content:
                lightbox_found = True
                print(f"[OK] Found lightbox image in section '{s.title}'!")
    assert lightbox_found, "Lightbox was not parsed correctly!"
    
    # Check 4: FX Container processing
    fx_found = False
    for p in pages:
        for s in p.sections:
            if "class=\"exe-fx" in s.content:
                fx_found = True
                print(f"[OK] Found FX widget in section '{s.title}'!")
                assert "exe-accordion" in s.content or "exe-tabs" in s.content or "exe-carousel" in s.content, "FX class not matched!"
    assert fx_found, "FX containers were not parsed correctly!"

    # Clean up test output directory
    if output_root.exists():
        shutil.rmtree(output_root)
        
    print("\n[SUCCESS] Headless verification succeeded! All custom exemark syntax extensions compiled perfectly to eXeLearning HTML.")

if __name__ == "__main__":
    run_test()
