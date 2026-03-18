import mammoth
import re
import shutil
import os
from pathlib import Path
from bs4 import BeautifulSoup
from unicodedata import normalize
import string
import random
from datetime import datetime
import html
import json
import time
import threading
import copy
import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import filedialog
from flask import Flask, send_from_directory, jsonify, send_file
from flask_cors import CORS
import logging

# Silence Flask logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# --- GLOBALS ---
LAST_UPDATE = time.time()
CURRENT_OUT_PATH = None

# Detect best available parser
try:
    import lxml
    BEST_PARSER = "lxml"
except ImportError:
    BEST_PARSER = "html.parser"

import sys

# --- CONFIGURATION & PATHS ---
def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = Path(sys._MEIPASS)
    except Exception:
        base_path = Path(__file__).resolve().parent

    return base_path / relative_path

BASE_DIR = Path(__file__).resolve().parent
SDA_TEMPLATE_DIR = resource_path("template")
CURRENT_OUT_PATH = None
INPUT_DIR = BASE_DIR / "input"
OUTPUT_ROOT = BASE_DIR / "output"

# Document-level metadata keys (lowercase) -> content.xml property keys
DOC_METADATA_KEYS = {
    "titulo": "pp_title",
    "título": "pp_title",
    "subtitulo": "pp_subtitle",
    "subtítulo": "pp_subtitle",
    "idioma": "pp_lang",
    "autoria": "pp_author",
    "autoría": "pp_author",
    "licencia": "license",
    "descripcion": "pp_description",
    "descripción": "pp_description",
}

# Language name -> ISO 639-1 code
LANGUAGE_MAP = {
    "valencià": "va", "valenciano": "va", "catalán": "ca", "català": "ca",
    "castellano": "es", "español": "es", "spanish": "es",
    "english": "en", "inglés": "en", "anglès": "en",
    "français": "fr", "francés": "fr", "french": "fr",
    "português": "pt", "portugués": "pt",
    "deutsch": "de", "alemán": "de", "german": "de",
    "italiano": "it", "italian": "it",
    "galego": "gl", "gallego": "gl",
    "euskara": "eu", "vasco": "eu", "euskera": "eu",
}
MAIN_DOCX = INPUT_DIR / "exelearning.docx"
CONTENT_DIR = OUTPUT_ROOT / "content"

def slugify(text):
    """Converts a string to a URL-friendly slug."""
    text = normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    text = re.sub(r'[^\w\s-]', '', text).strip()
    return re.sub(r'[-\s]+', '-', text)

def generate_id():
    """Generates a unique eXeLearning ID: timestamp + 6 random uppercase chars."""
    now = datetime.now().strftime("%Y%m%d%H%M%S")
    suffix = ''.join(random.choices(string.ascii_uppercase, k=6))
    return f"{now}{suffix}"

def extract_theme_name(theme_path):
    """Extracts theme name from config.xml in the theme folder."""
    config_path = theme_path / "config.xml"
    if not config_path.exists():
        return theme_path.name
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "xml")
            name_tag = soup.find("name")
            if name_tag:
                return name_tag.get_text().strip()
    except Exception:
        pass
    return theme_path.name

class Page:
    def __init__(self, title, level=1, existing_slugs=None):
        self.id = generate_id()
        self.title = title
        self.level = level
        self.sections = [] # List of {"block_id": str, "component_id": str, "title": str, "content": str}
        base_slug = slugify(title)
        
        # Ensure unique slug and avoid reserved names for sub-pages
        self.slug = base_slug
        reserved = {"index", "portada"}
        
        if existing_slugs is not None:
            # If this is the first page, it will become index.html regardless of slug
            # but we should still record its slug.
            counter = 1
            # For non-first pages, if slug is reserved or exists, append counter
            # Actually, let's just make it unique.
            while self.slug in existing_slugs or (len(existing_slugs) > 0 and self.slug in reserved):
                self.slug = f"{base_slug}-{counter}"
                counter += 1
            existing_slugs.add(self.slug)

        self.filename = f"{self.slug}.html" if self.slug != "index" and self.slug != "portada" else "index.html"
        self.children = []
        self.parent = None

    def add_content(self, html_str):
        if not self.sections:
            self.add_section("")
        self.sections[-1]["content"] += html_str

    def add_metadata(self, key, value):
        """Adds a {Key: Value} metadata pair to the current section."""
        if not self.sections:
            self.add_section("")
        section = self.sections[-1]
        if not section["metadata_duration_label"]:
            section["metadata_duration_label"] = key
            section["metadata_duration_value"] = value
        elif not section["metadata_participants_label"]:
            section["metadata_participants_label"] = key
            section["metadata_participants_value"] = value

    def add_section(self, title):
        self.sections.append({
            "block_id": generate_id(),
            "component_id": generate_id(),
            "title": title,
            "content": "",
            "metadata_duration_label": "",
            "metadata_duration_value": "",
            "metadata_participants_label": "",
            "metadata_participants_value": "",
        })

def process_links(soup, input_dir, output_root, section_id):
    """Processes links and YouTube embeds in-place on a BeautifulSoup object."""
    # 1. YouTube
    yt_regex = re.compile(r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]+))')
    for a in soup.find_all('a', href=True):
        href = a['href']
        yt_match = yt_regex.search(href)
        if yt_match:
            video_id = yt_match.group(2)
            # Create eXeLearning style video embed
            video_container = soup.new_tag("div", **{"class": "exe-video-wrapper exe-video-center exe-video-fixed", "style": "width:560px;"})
            iframe = soup.new_tag("iframe", **{
                "width": "560", "height": "315", "src": f"https://www.youtube.com/embed/{video_id}",
                "frameborder": "0", "allowfullscreen": "allowfullscreen"
            })
            video_container.append(iframe)
            a.replace_with(video_container)
            continue
            
        # 2. Local Files
        file_name = Path(href).name
        local_file_path = input_dir / file_name
        if local_file_path.exists() and local_file_path.is_file():
            resource_folder = output_root / "content" / "resources" / section_id
            resource_folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_file_path, resource_folder / file_name)
            a['href'] = f"{{REL_PREFIX}}content/resources/{section_id}/{file_name}"
            a['target'] = "_blank"
            if a.get('rel') != "lightbox":
                a['rel'] = "noopener"

    return soup

def extract_docx_image_dimensions(docx_path):
    """Parses word/document.xml to find image dimensions (in px)."""
    import zipfile
    dims = []
    try:
        with zipfile.ZipFile(docx_path, 'r') as docx:
            if 'word/document.xml' in docx.namelist():
                doc_xml = docx.read('word/document.xml').decode('utf-8')
                # Look for <wp:extent cx="123" cy="456" />
                # 1 px (96dpi) = 9,525 EMUs
                extents = re.findall(r'<wp:extent\s+cx="(\d+)"\s+cy="(\d+)"', doc_xml)
                for cx, cy in extents:
                    width_px = int(cx) / 9525
                    height_px = int(cy) / 9525
                    dims.append((round(width_px), round(height_px)))
    except Exception as e:
        print(f"[Warning] Error extracting dimensions from XML: {e}")
    return dims

def process_lightboxes(soup):
    """Finds {lightbox} tags and wraps the subsequent <img> in a lightbox link."""
    link_counter = 0
    for text_node in soup.find_all(string=re.compile(r"\{lightbox\}")):
        # Get the text and parent before removal
        parent = text_node.parent
        
        # Remove the tag from the text
        new_text = text_node.replace("{lightbox}", "").strip()
        if not new_text:
            text_node.extract()
        else:
            text_node.replace_with(new_text)

        # Now find the next img in the document starting from the parent
        next_img = parent.find_next("img")
        if next_img:
            # Ensure img has alt attribute
            if not next_img.get('alt'):
                next_img['alt'] = ""

            # Check if this image is already in a link
            current = next_img.parent
            is_wrapped = False
            while current and current.name != 'body':
                if current.name == 'a':
                    is_wrapped = True
                    if not current.get('rel'):
                        current['rel'] = "lightbox"
                    elif "lightbox" not in current['rel']:
                        current['rel'] = f"{current['rel']} lightbox".strip()
                    # Add lightbox attributes
                    current['id'] = f"link_{link_counter}"
                    link_counter += 1
                    break
                current = current.parent
            
            if not is_wrapped:
                # Wrap the image in an <a> tag with lightbox attributes
                a_tag = soup.new_tag("a", href=next_img['src'], rel="lightbox",
                                     id=f"link_{link_counter}")
                link_counter += 1
                next_img.wrap(a_tag)
                current = a_tag  # for clearfix below

            # Add <p class="clearfix"></p> after the lightbox wrapper's parent <p>
            lightbox_p = next_img.find_parent("p")
            if lightbox_p:
                clearfix_p = soup.new_tag("p", **{"class": "clearfix"})
                lightbox_p.insert_after(clearfix_p)

    return soup

def process_content_resources(soup, output_root, section_id):
    """Moves images from temp_media to section-specific folder and updates paths."""
    temp_folder = output_root / "content" / "resources" / "temp_media"
    resource_folder = output_root / "content" / "resources" / section_id
    
    # 1. Process <img> tags
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "content/resources/temp_media/" in src:
            file_name = src.split("/")[-1]
            src_path = temp_folder / file_name
            if src_path.exists():
                resource_folder.mkdir(parents=True, exist_ok=True)
                shutil.move(src_path, resource_folder / file_name)
                img["src"] = f"{{REL_PREFIX}}content/resources/{section_id}/{file_name}"

    # 2. Process lightbox links (<a> tags with rel="lightbox")
    for a in soup.find_all("a", rel=re.compile(r"lightbox")):
        href = a.get("href", "")
        if "content/resources/temp_media/" in href:
            file_name = href.split("/")[-1]
            src_path = temp_folder / file_name
            if src_path.exists():
                resource_folder.mkdir(parents=True, exist_ok=True)
                shutil.move(src_path, resource_folder / file_name)
        elif f"content/resources/{section_id}/" in href:
            # Already moved by <img> processing above
            file_name = href.split("/")[-1]
        else:
            continue

        # Create _1 duplicate for original/full-size (lightbox href)
        name_base, ext = os.path.splitext(file_name)
        original_name = f"{name_base}_1{ext}"
        resource_folder.mkdir(parents=True, exist_ok=True)
        src_file = resource_folder / file_name
        dst_file = resource_folder / original_name
        if src_file.exists() and not dst_file.exists():
            shutil.copy2(src_file, dst_file)
        
        # Calculate file size for title/size attributes
        file_size_str = ""
        if dst_file.exists():
            size_bytes = dst_file.stat().st_size
            file_size_str = f"{size_bytes / 1024:.2f} KB"
        
        # Update href to point to the _1 original copy
        a["href"] = f"{{REL_PREFIX}}content/resources/{section_id}/{original_name}"
        a["title"] = original_name
        a["size"] = file_size_str
        
        # Update the img src to the thumbnail (original filename)
        img_tag = a.find("img")
        if img_tag:
            img_tag["src"] = f"{{REL_PREFIX}}content/resources/{section_id}/{file_name}"

    return soup

def parse_html_fragment(html_str):
    """Fast parsing of HTML fragments."""
    return BeautifulSoup(html_str, BEST_PARSER)

def extract_pages_from_docx(docx_path, input_dir, output_root):
    """Extracts content from docx. Uses a temp copy to bypass Word locks."""
    temp_docx = output_root / "temp_watch.docx"
    max_retries = 5
    last_err = None
    
    for i in range(max_retries):
        try:
            shutil.copy2(docx_path, temp_docx)
            break
        except Exception as e:
            last_err = e
            time.sleep(0.5)
    else:
        print(f"[Error] Could not read {docx_path.name}: {last_err}")
        return []

    images_folder = output_root / "content" / "resources" / "temp_media"
    images_folder.mkdir(parents=True, exist_ok=True)
    
    # 3. Extract dimensions from XML (Mammoth doesn't provide them)
    docx_dims = extract_docx_image_dimensions(temp_docx)
    image_count = 0

    def convert_image(image):
        nonlocal image_count
        image_count += 1
        extension = image.content_type.partition("/")[2]
        file_name = f"image_{image_count}.{extension}"
        
        with image.open() as image_bytes:
            with open(images_folder / file_name, "wb") as f:
                f.write(image_bytes.read())
        
        # Use a placeholder for the prefix, similarly to REL_PREFIX
        img_attrs = {"src": f"{{REL_PREFIX}}content/resources/temp_media/{file_name}"}
        
        # Apply dimensions if we have them from the XML list
        if image_count <= len(docx_dims):
            w, h = docx_dims[image_count - 1]
            img_attrs["width"] = str(w)
            img_attrs["height"] = str(h)
            
        return img_attrs

    try:
        with open(temp_docx, "rb") as docx_file:
            result = mammoth.convert_to_html(docx_file, convert_image=mammoth.images.img_element(convert_image))
            full_html = result.value
    finally:
        if temp_docx.exists():
            try: os.remove(temp_docx)
            except: pass
    
    soup = BeautifulSoup(full_html, BEST_PARSER)
    process_lightboxes(soup)
    
    pages = []
    existing_slugs = set()
    current_page = None
    doc_metadata = {}  # Document-level metadata (before any page marker)
    collecting_description = False  # For multi-line {descripción: ...}
    collecting_accordion = False
    accordion_elements = []
    
    page_marker_regex = re.compile(r"^(#+)\s*(.+)$")
    section_marker_regex = re.compile(r"^%\s*(.+)$")
    metadata_regex = re.compile(r"^\{(.+?):\s*(.+?)\}$")
    # Multi-line metadata: opening line without closing brace
    metadata_open_regex = re.compile(r"^\{(.+?):\s*(.+)$")

    section_elements = []

    # Initial section
    section_elements = []

    def flush_section():
        if not current_page or not section_elements: return
        # Combine elements and process links once per section
        section_soup = BeautifulSoup("", BEST_PARSER)
        for el in section_elements:
            section_soup.append(copy.deepcopy(el))
        
        # Ensure at least one section exists to receive the content
        if not current_page.sections:
            current_page.add_section("")
            
        section_id = current_page.sections[-1]["component_id"]
        process_content_resources(section_soup, output_root, section_id)
        process_links(section_soup, input_dir, output_root, section_id)
        current_page.add_content(str(section_soup))
        section_elements.clear()

    # Pre-create a default page if the document starts without a marker
    default_page = Page("Portada", 1)
    default_page.filename = "index.html"
    current_page = default_page
    pages.append(current_page)
    # We will remove it later if a real # marker is found as the first thing
    is_default_page_active = True

    # Ensure we iterate over the actual content elements
    body = soup.find("body")
    elements = body.contents if body else soup.contents
    
    with open("tmp_debug.txt", "w", encoding="utf-8") as debug_file:
        for element in elements:
            if not element.name:
                if not current_page and not collecting_description:
                    continue  # Skip whitespace before any page
                if collecting_accordion:
                    accordion_elements.append(element)
                else:
                    section_elements.append(element)
                continue
                
            text = element.get_text().strip()
            debug_file.write(f"Element: {element.name}, Text: [{text}]\n")
            
            # Handle multi-line description continuation
            if collecting_description:
                # Check if this line ends the description with }
                if text.endswith("}"):
                    doc_metadata["pp_description"] += "\n" + text[:-1].rstrip()
                    collecting_description = False
                else:
                    doc_metadata["pp_description"] += "\n" + text
                continue

            # Handle accordion block
            # More permissive matching for {acordeon}
            if re.search(r"\{acorde[oó]n\}", text, re.I):
                collecting_accordion = True
                accordion_elements = []
                debug_file.write("Match: START ACCORDION\n")
                continue
            
            if re.search(r"\{fin\s+acorde[oó]n\}", text, re.I):
                if collecting_accordion:
                    debug_file.write("Match: END ACCORDION\n")
                    accordion_div = soup.new_tag("div", attrs={"class": "exe-fx exe-accordion"})
                    for acc_el in accordion_elements:
                        if not acc_el.name: 
                            accordion_div.append(copy.deepcopy(acc_el))
                            continue
                        el_text = acc_el.get_text().strip()
                        # Match ">> Title", "> > Title", etc.
                        if (acc_el.name.startswith("h") or acc_el.name == "p") and re.match(r"^>\s*>\s*.+", el_text):
                            h2 = soup.new_tag("h2")
                            # Strip the >> and any leading/trailing spaces
                            h2.string = re.sub(r"^>\s*>\s*", "", el_text).strip()
                            accordion_div.append(h2)
                        else:
                            accordion_div.append(copy.deepcopy(acc_el))
                    section_elements.append(accordion_div)
                    collecting_accordion = False
                    accordion_elements = []
                continue
                
            if collecting_accordion:
                accordion_elements.append(element)
                continue
        
            page_match = page_marker_regex.match(text)
            if page_match:
                # If this is the first real marker and we were using a default page with no content, 
                # replace the default page.
                if is_default_page_active and not any(s["content"] for s in default_page.sections) and not section_elements:
                    pages.remove(default_page)
                    existing_slugs.discard(default_page.slug)
                
                flush_section()
                is_default_page_active = False # Found a real marker
                level = len(page_match.group(1))
                title = page_match.group(2).strip()
                new_page = Page(title, level, existing_slugs)
                if not pages: new_page.filename = "index.html"
                pages.append(new_page)
                current_page = new_page
                continue
                
            section_match = section_marker_regex.match(text)
            if section_match:
                flush_section()
                section_title = section_match.group(1).strip()
                if current_page: current_page.add_section(section_title)
                continue

            # Check for metadata (both document-level and section-level)
            metadata_match = metadata_regex.match(text)
            if metadata_match:
                key = metadata_match.group(1).strip()
                value = metadata_match.group(2).strip()
                prop_key = DOC_METADATA_KEYS.get(key.lower())
                
                if prop_key and not current_page:
                    # Document-level metadata (before any # page marker)
                    if prop_key == "pp_lang":
                        value = LANGUAGE_MAP.get(value.lower(), value)
                    doc_metadata[prop_key] = value
                elif current_page:
                    # Section-level metadata (duration/participants)
                    current_page.add_metadata(key, value)
                continue
            
            # Check for multi-line metadata opening (no closing brace)
            if not current_page:
                metadata_open_match = metadata_open_regex.match(text)
                if metadata_open_match:
                    key = metadata_open_match.group(1).strip()
                    value = metadata_open_match.group(2).strip()
                    prop_key = DOC_METADATA_KEYS.get(key.lower())
                    if prop_key:
                        doc_metadata[prop_key] = value
                        collecting_description = True
                    continue
                
            if current_page:
                section_elements.append(element)

    flush_section()

    # If the default page was created but never got content (only page markers), remove it
    if is_default_page_active and not any(s["content"] for s in default_page.sections) and len(pages) > 1:
        pages.remove(default_page)
        
    # Final cleanup of temp image folder
    temp_media = output_root / "content" / "resources" / "temp_media"
    if temp_media.exists():
        try: shutil.rmtree(temp_media)
        except: pass

    return build_hierarchy(pages), doc_metadata

def build_hierarchy(flat_pages):
    """Reconstructs the parent-child relationships from flat list levels."""
    if not flat_pages: return []
    last_pages_by_level = {}
    for p in flat_pages:
        level = p.level
        last_pages_by_level[level] = p
        if level > 1:
            parentLevel = level - 1
            while parentLevel > 0 and parentLevel not in last_pages_by_level:
                parentLevel -= 1
            if parentLevel > 0:
                parent = last_pages_by_level[parentLevel]
                p.parent = parent
                parent.children.append(p)
    return flat_pages

def generate_site_nav(all_pages):
    """Generates the base siteNav HTML with placeholders for active state."""
    roots = [p for p in all_pages if p.parent is None]
    def build_list(nodes):
        if not nodes: return ""
        html_ul = "<ul>\n"
        for node in nodes:
            rel_path = "index.html" if node.filename == "index.html" else f"html/{node.filename}"
            # Placeholder for active class: [[ACTIVE_]] + node_id
            html_ul += f'<li><a href="{{REL_PREFIX}}{rel_path}" class="no-ch [[ACTIVE_{node.id}]]"><span>{node.title}</span></a>'
            if node.children:
                html_ul += build_list(node.children)
            html_ul += "</li>\n"
        html_ul += "</ul>\n"
        return html_ul
    return f'<nav id="siteNav">\n{build_list(roots)}\n</nav>'

def write_file(path, content):
    """Helper for parallel file writing."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def generate_content_xml(pages, package_title, description="", doc_metadata=None, theme_name="base"):
    """Generates the content.xml manifest for the eXeLearning project."""
    if doc_metadata is None:
        doc_metadata = {}
    
    proj_id = generate_id()
    version_id = generate_id()
    
    # Use doc_metadata values if available, otherwise use defaults
    title = html.escape(doc_metadata.get("pp_title", package_title))
    subtitle = html.escape(doc_metadata.get("pp_subtitle", ""))
    lang = html.escape(doc_metadata.get("pp_lang", "va"))
    author = html.escape(doc_metadata.get("pp_author", "Autor del recurs"))
    license_val = html.escape(doc_metadata.get("license", "creative commons: attribution - share alike 4.0"))
    desc = html.escape(doc_metadata.get("pp_description", description))
    
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<ode xmlns="http://www.intef.es/xsd/ode" version="2.0">
    <userPreferences>
        <userPreference><key>theme</key><value>{html.escape(theme_name)}</value></userPreference>
    </userPreferences>
    <odeResources>
        <odeResource><key>odeVersionId</key><value>{version_id}</value></odeResource>
        <odeResource><key>odeId</key><value>{proj_id}</value></odeResource>
        <odeResource><key>odeVersionName</key><value>0</value></odeResource>
        <odeResource><key>isDownload</key><value>true</value></odeResource>
        <odeResource><key>eXeVersion</key><value>v3.0.2</value></odeResource>
    </odeResources>
    <odeProperties>
        <odeProperty><key>pp_title</key><value>{title}</value></odeProperty>
        <odeProperty><key>pp_subtitle</key><value>{subtitle}</value></odeProperty>
        <odeProperty><key>pp_lang</key><value>{lang}</value></odeProperty>
        <odeProperty><key>pp_author</key><value>{author}</value></odeProperty>
        <odeProperty><key>license</key><value>{license_val}</value></odeProperty>
        <odeProperty><key>pp_description</key><value>{desc}</value></odeProperty>
        <odeProperty><key>exportSource</key><value>true</value></odeProperty>
        <odeProperty><key>pp_addExeLink</key><value>true</value></odeProperty>
        <odeProperty><key>pp_addPagination</key><value>false</value></odeProperty>
        <odeProperty><key>pp_addSearchBox</key><value>false</value></odeProperty>
        <odeProperty><key>pp_addAccessibilityToolbar</key><value>false</value></odeProperty>
        <odeProperty><key>pp_extraHeadContent</key><value></value></odeProperty>
        <odeProperty><key>footer</key><value></value></odeProperty>
    </odeProperties>
    <odeNavStructures>
"""

    for i, page in enumerate(pages, 1):
        parent_id = page.parent.id if page.parent else ""
        xml += f"""        <odeNavStructure>
            <odePageId>{page.id}</odePageId>
            <odeParentPageId>{parent_id}</odeParentPageId>
            <pageName>{html.escape(page.title)}</pageName>
            <odeNavStructureOrder>{i}</odeNavStructureOrder>
            <odeNavStructureProperties>
                <odeNavStructureProperty><key>titlePage</key><value>{html.escape(page.title)}</value></odeNavStructureProperty>
                <odeNavStructureProperty><key>titleNode</key><value>{html.escape(page.title)}</value></odeNavStructureProperty>
                <odeNavStructureProperty><key>hidePageTitle</key><value>false</value></odeNavStructureProperty>
                <odeNavStructureProperty><key>titleHtml</key><value></value></odeNavStructureProperty>
                <odeNavStructureProperty><key>editableInPage</key><value>false</value></odeNavStructureProperty>
                <odeNavStructureProperty><key>visibility</key><value>true</value></odeNavStructureProperty>
                <odeNavStructureProperty><key>highlight</key><value>false</value></odeNavStructureProperty>
                <odeNavStructureProperty><key>description</key><value></value></odeNavStructureProperty>
            </odeNavStructureProperties>
            <odePagStructures>
"""
        for j, section in enumerate(page.sections, 1):
            block_name = html.escape(section["title"]) if section["title"] else " "
            icon = ""
            if any(k in block_name.lower() for k in ["reto", "objetivos", "mision"]): icon = "objectives"
            
            # Prepare content for XML: transform resource paths to {{context_path}}
            xml_content = section["content"].replace("{REL_PREFIX}content/resources/", f"{{{{context_path}}}}/")
            xml_content = xml_content.replace(f"content/resources/{section['component_id']}/", f"{{{{context_path}}}}/{section['component_id']}/")

            # Build metadata <dl> block if present
            dl_block = ""
            duration_label = section["metadata_duration_label"]
            duration_value = section["metadata_duration_value"]
            participants_label = section["metadata_participants_label"]
            participants_value = section["metadata_participants_value"]
            
            if duration_label or participants_label:
                dl_items = ""
                if duration_label:
                    dl_items += (f'<div class="inline"><dt><span title="{html.escape(duration_label)}">'
                                 f'{html.escape(duration_label)}</span></dt>'
                                 f'<dd>{html.escape(duration_value)}</dd></div>')
                if participants_label:
                    dl_items += (f'<div class="inline"><dt><span title="{html.escape(participants_label)}">'
                                 f'{html.escape(participants_label)}</span></dt>'
                                 f'<dd>{html.escape(participants_value)}</dd></div>')
                dl_block = f'<dl>{dl_items}</dl>'

            inner_html = (
                f'<div class="exe-text-template"><div class="textIdeviceContent">'
                f'<div class="exe-text-activity"><div>{dl_block}{xml_content}</div></div>'
                f'</div></div>'
            )
            
            json_props = json.dumps({
                "ideviceId": section["component_id"],
                "textInfoDurationInput": duration_value,
                "textInfoDurationTextInput": duration_label or "Duración",
                "textInfoParticipantsInput": participants_value,
                "textInfoParticipantsTextInput": participants_label or "Agrupamiento",
                "textTextarea": xml_content,
                "textFeedbackInput": "Mostra la retroacció",
                "textFeedbackTextarea": ""
            })

            xml += f"""                <odePagStructure>
                    <odePageId>{page.id}</odePageId>
                    <odeBlockId>{section["block_id"]}</odeBlockId>
                    <blockName>{block_name}</blockName>
                    <iconName>{icon}</iconName>
                    <odePagStructureOrder>{j}</odePagStructureOrder>
                    <odePagStructureProperties>
                        <odePagStructureProperty><key>visibility</key><value>true</value></odePagStructureProperty>
                        <odePagStructureProperty><key>teacherOnly</key><value>false</value></odePagStructureProperty>
                        <odePagStructureProperty><key>allowToggle</key><value>true</value></odePagStructureProperty>
                        <odePagStructureProperty><key>minimized</key><value>false</value></odePagStructureProperty>
                        <odePagStructureProperty><key>identifier</key><value></value></odePagStructureProperty>
                        <odePagStructureProperty><key>cssClass</key><value></value></odePagStructureProperty>
                    </odePagStructureProperties>
                    <odeComponents>
                        <odeComponent>
                            <odePageId>{page.id}</odePageId>
                            <odeBlockId>{section["block_id"]}</odeBlockId>
                            <odeIdeviceId>{section["component_id"]}</odeIdeviceId>
                            <odeIdeviceTypeName>text</odeIdeviceTypeName>
                            <htmlView>{html.escape(inner_html)}</htmlView>
                            <jsonProperties>{html.escape(json_props)}</jsonProperties>
                            <odeComponentsOrder>1</odeComponentsOrder>
                            <odeComponentsProperties>
                                <odeComponentsProperty><key>visibility</key><value>true</value></odeComponentsProperty>
                                <odeComponentsProperty><key>teacherOnly</key><value>false</value></odeComponentsProperty>
                                <odeComponentsProperty><key>identifier</key><value></value></odeComponentsProperty>
                                <odeComponentsProperty><key>cssClass</key><value></value></odeComponentsProperty>
                            </odeComponentsProperties>
                        </odeComponent>
                    </odeComponents>
                </odePagStructure>
"""
        xml += "            </odePagStructures>\n        </odeNavStructure>\n"

    xml += """    </odeNavStructures>
</ode>
"""
    return xml

def create_exelearning_package(pages, output_root, target_update, doc_metadata=None, theme_path=None, theme_name="base"):
    """Creates the folder structure and generates all HTML files. Optimized for speed."""
    if not SDA_TEMPLATE_DIR.exists():
        print(f"Error: Template directory 'template' not found at {SDA_TEMPLATE_DIR}")
        return

    # If a custom theme is provided, copy it over the template theme
    if theme_path and theme_path.is_dir():
        shutil.copytree(theme_path, output_root / "theme", dirs_exist_ok=True)

    # 1. Pre-parse template and cache common elements
    with open(SDA_TEMPLATE_DIR / "index.html", "r", encoding="utf-8") as f:
        soup_template = BeautifulSoup(f.read(), BEST_PARSER)
    
    package_title_tag = soup_template.find("h1", class_="package-title")
    package_title_template = package_title_tag.get_text() if package_title_tag else "Proyecto eXeLearning"
    
    # Priority: Metadata > Template Header > Default
    if doc_metadata and "pp_title" in doc_metadata:
        package_title = doc_metadata["pp_title"]
        if package_title_tag:
            package_title_tag.string = package_title
    else:
        package_title = package_title_template

    # 1.1 Inject Lightbox assets into template head
    if soup_template.head:
        # Use {REL_PREFIX} so the path processing loop handles it correctly for subpages
        lb_css = soup_template.new_tag("link", rel="stylesheet", **{"type": "text/css", "href": "{REL_PREFIX}libs/exe_lightbox/exe_lightbox.css"})
        lb_js = soup_template.new_tag("script", **{"type": "text/javascript", "src": "{REL_PREFIX}libs/exe_lightbox/exe_lightbox.js"})
        soup_template.head.append(lb_css)
        soup_template.head.append(lb_js)

    # Pre-parse all sections into soup once
    for page in pages:
        for section in page.sections:
            section["soup"] = parse_html_fragment(section["content"])

    # Pre-generate the auto-reload script
    reload_script_html = f"""
    <script>
        window.lastUpdate = window.lastUpdate || {int(target_update * 1000)};
        setInterval(async () => {{
            try {{
                const res = await fetch('/status');
                const data = await res.json();
                if (data.last_update > window.lastUpdate) {{
                    window.location.reload();
                }}
            }} catch (e) {{}}
        }}, 500);
    </script>
    """
    reload_script_soup = parse_html_fragment(reload_script_html)

    # 2. Generate pages and prepare for parallel write
    write_tasks = []
    
    # Pre-generate base nav without active classes for faster page generation
    base_nav_raw = generate_site_nav(pages)

    for page in pages:
        page_soup = copy.deepcopy(soup_template)
        
        if page_soup.title: page_soup.title.string = f"{page.title} | {package_title}"
        page_title_h2 = page_soup.find("h2", class_="page-title")
        if page_title_h2: page_title_h2.string = page.title
            
        nav_placeholder = page_soup.find("nav", id="siteNav")
        content_placeholder = page_soup.find("div", class_="page-content")
        
        if content_placeholder:
            for article in content_placeholder.find_all("article"): article.decompose()
            for section in page.sections:
                article_tag = page_soup.new_tag("article", **{"class": "box", "id": section["block_id"]})
                if not section["title"]:
                    article_tag["class"] = "box no-header"
                else:
                    head = page_soup.new_tag("header", **{"class": "box-head"})
                    icon_div = page_soup.new_tag("div", **{"class": "box-icon exe-icon"})
                    icon_name = "draw.png"
                    if any(k in section["title"].lower() for k in ["reto", "objetivos", "mision"]): icon_name = "objectives.png"
                    elif any(k in section["title"].lower() for k in ["lectura", "texto", "leer"]): icon_name = "reading.png"
                    
                    icon_img = page_soup.new_tag("img", **{"src": f"theme/icons/{icon_name}", "alt": ""})
                    icon_div.append(icon_img)
                    head.append(icon_div)
                    
                    title_h1 = page_soup.new_tag("h1", **{"class": "box-title"})
                    title_h1.string = section["title"]
                    head.append(title_h1)
                    
                    toggle_btn = page_soup.new_tag("button", **{"class": "box-toggle box-toggle-on", "title": "Ocultar/Mostrar contenido"})
                    span_tag = page_soup.new_tag("span")
                    span_tag.string = "Ocultar/Mostrar contenido"
                    toggle_btn.append(span_tag)
                    head.append(toggle_btn)
                    article_tag.append(head)
                
                box_content = page_soup.new_tag("div", **{"class": "box-content"})
                
                # Create the complex eXeLearning iDevice structure
                idevice_node = page_soup.new_tag("div", **{
                    "id": section["component_id"],
                    "class": "idevice_node text loaded",
                    "data-idevice-path": "idevices/text/",
                    "data-idevice-type": "text",
                    "data-idevice-component-type": "json"
                })
                
                inner_template = page_soup.new_tag("div", **{"class": "exe-text-template"})
                text_content = page_soup.new_tag("div", **{"class": "textIdeviceContent"})
                activity_wrapper = page_soup.new_tag("div", **{"class": "exe-text-activity"})
                inner_div = page_soup.new_tag("div")
                
                inner_div.extend(copy.deepcopy(section["soup"]).contents)
                activity_wrapper.append(inner_div)
                text_content.append(activity_wrapper)
                inner_template.append(text_content)
                idevice_node.append(inner_template)
                
                box_content.append(idevice_node)
                article_tag.append(box_content)
                content_placeholder.append(article_tag)

        # Update relative paths and nav
        prefix = "" if page.filename == "index.html" else "../"
        
        # Link and Image path processing (must happen for ALL pages to resolve {REL_PREFIX})
        for tag in page_soup.find_all(["link", "script", "img", "a"], recursive=True):
            for attr in ["href", "src"]:
                if tag.has_attr(attr):
                    val = tag[attr]
                    if "{REL_PREFIX}" in val:
                        tag[attr] = val.replace("{REL_PREFIX}", prefix)
                    elif page.filename != "index.html" and not val.startswith(("http", "https", "#", "data:", "/")):
                        tag[attr] = prefix + val

        if nav_placeholder:
            # 1. Set current page as active
            page_nav_html = base_nav_raw.replace(f"[[ACTIVE_{page.id}]]", "active")
            # 2. Clear all other placeholders and set prefix
            page_nav_html = re.sub(r"\[\[ACTIVE_[\w-]+\]\]", "", page_nav_html)
            page_nav_html = page_nav_html.replace("{REL_PREFIX}", prefix)
            
            nav_placeholder.replace_with(BeautifulSoup(page_nav_html, BEST_PARSER))

        if page_soup.body:
            page_soup.body.append(copy.deepcopy(reload_script_soup))

        output_path = (output_root if page.filename == "index.html" else output_root / "html") / page.filename
        write_tasks.append((output_path, str(page_soup)))

    # 3. Generate content.xml and finalize
    description_meta = soup_template.find("meta", attrs={"name": "description"})
    desc_text = description_meta["content"] if description_meta else ""
    content_xml = generate_content_xml(pages, package_title, desc_text, doc_metadata, theme_name)
    write_tasks.append((output_root / "content.xml", content_xml))

    # Parallel write
    with ThreadPoolExecutor() as executor:
        for path, content in write_tasks:
            executor.submit(write_file, path, content)

def prepare_output(output_root):
    """Initializes output directory with template assets."""
    output_root.mkdir(parents=True, exist_ok=True)
    if not SDA_TEMPLATE_DIR.exists():
        print(f"[Warning] Template dir not found at {SDA_TEMPLATE_DIR}")
        return

    for folder in ["libs", "theme", "idevices", "content", "custom"]:
        src = SDA_TEMPLATE_DIR / folder
        dst = output_root / folder
        if src.exists():
            # Copy if missing or merge if exists
            shutil.copytree(src, dst, dirs_exist_ok=True)
    
    (output_root / "html").mkdir(exist_ok=True)

def run_conversion(docx_path, input_dir, output_root):
    """Full conversion flow. Optimized and instrumented."""
    if docx_path.exists():
        start_time = time.time()
        timestamp_str = datetime.now().strftime("%H:%M:%S")
        try:
            # 1. Determine the target timestamp for THIS generation
            target_update = time.time()
            
            # 2. Extract (Mammoth + BeautifulSoup extraction)
            t0 = time.time()
            pages, doc_metadata = extract_pages_from_docx(docx_path, input_dir, output_root)
            t_extract = time.time() - t0
            
            # Detect custom theme
            theme_path = docx_path.parent / "theme"
            theme_name = "base"
            if theme_path.is_dir():
                theme_name = extract_theme_name(theme_path)
            
            # 3. Create package (HTML injection + Disk writing)
            t0 = time.time()
            create_exelearning_package(pages, output_root, target_update, doc_metadata, theme_path, theme_name)
            t_package = time.time() - t0
            
            # 4. ONLY NOW update the global status so the browser reloads
            global LAST_UPDATE
            LAST_UPDATE = target_update
            
            duration = time.time() - start_time
            print(f"[{timestamp_str}] ✅ Conversión completada en {duration:.2f}s (Ext: {t_extract:.2f}s, Pkg: {t_package:.2f}s)")
        except Exception as e:
            print(f"[{timestamp_str}] ❌ Error en conversión: {e}")
            import traceback
            traceback.print_exc()

# --- WEB SERVER ---
app = Flask(__name__)
CORS(app)

@app.route("/")
def serve_index():
    print(f"[Server] Request for / (index.html) in {CURRENT_OUT_PATH}")
    if CURRENT_OUT_PATH is None:
        return "Error: Output path not set", 500
    index_path = CURRENT_OUT_PATH / "index.html"
    if not index_path.exists():
        print(f"[Server ERROR] index.html not found at {index_path}")
        return f"Not Found: {index_path} does not exist. Please check if conversion worked.", 404
    return send_from_directory(CURRENT_OUT_PATH.resolve(), "index.html")

@app.route("/html/<path:path>")
def serve_html(path):
    print(f"[Server] Request for /html/{path}")
    return send_from_directory((CURRENT_OUT_PATH / "html").resolve(), path)

@app.route("/status")
def get_status():
    return jsonify({"last_update": int(LAST_UPDATE * 1000)})

@app.route("/elpx")
def download_elpx():
    """Zips the output directory and serves it as a .elpx file."""
    if CURRENT_OUT_PATH is None or not CURRENT_OUT_PATH.exists():
        return "Error: Output directory not found", 404
        
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(CURRENT_OUT_PATH):
            for file in files:
                if file == "temp_watch.docx": continue
                file_path = Path(root) / file
                # Use relative path for the zip
                arcname = file_path.relative_to(CURRENT_OUT_PATH)
                zf.write(file_path, arcname)
    
    memory_file.seek(0)
    
    # Use the name of the docx or folder for the filename
    filename = "recurso.elpx"
    if CURRENT_OUT_PATH:
        # Parent of output is the work dir
        name = CURRENT_OUT_PATH.parent.name
        filename = f"{name}.elpx"

    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=filename
    )

@app.route("/<path:path>")
def serve_static(path):
    if CURRENT_OUT_PATH is None:
        return "Error", 500
    full_path = CURRENT_OUT_PATH / path
    if full_path.exists():
        return send_from_directory(CURRENT_OUT_PATH.resolve(), path)
    # print(f"[Server 404] Not found: {path}")
    return "Not Found", 404

def start_flask():
    app.run(host="127.0.0.1", port=5500, debug=False, use_reloader=False)

if __name__ == "__main__":
    # 1. Select Folder
    root = tk.Tk()
    root.withdraw()
    print("Por favor, selecciona la carpeta de trabajo...")
    folder_selected = filedialog.askdirectory(title="Selecciona la carpeta que contiene exelearning.docx")
    root.destroy()
    
    if not folder_selected:
        print("No se seleccionó ninguna carpeta. Saliendo.")
        exit()

    base_path = Path(folder_selected).resolve()
    # Find the first .docx file (excluding temp files)
    docx_files = [f for f in base_path.glob("*.docx") if not f.name.startswith("~$")]
    
    if not docx_files:
        print(f"Error: No se encontró ningún archivo .docx en {base_path}")
        exit()
        
    docx_file = docx_files[0]
    CURRENT_OUT_PATH = base_path / "output"
    print(f"Directorio de trabajo: {base_path}")
    print(f"Archivo detectado: {docx_file.name}")
    print(f"Carpeta de salida: {CURRENT_OUT_PATH}")

    # 2. Initial Conversion
    prepare_output(CURRENT_OUT_PATH)
    run_conversion(docx_file, base_path, CURRENT_OUT_PATH)

    # 3. Start Server in Thread
    threading.Thread(target=start_flask, daemon=True).start()
    print(f"\nServidor en vivo: http://localhost:5500")
    print(f"Observando cambios en: {docx_file}")

    # 4. Watch Loop
    try:
        last_mtime = docx_file.stat().st_mtime
    except:
        last_mtime = 0

    try:
        while True:
            time.sleep(0.5)
            try:
                if not docx_file.exists():
                    continue
                current_mtime = docx_file.stat().st_mtime
                if current_mtime > last_mtime:
                    last_mtime = current_mtime
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 📝 Cambio detectado en {docx_file.name}")
                    run_conversion(docx_file, base_path, CURRENT_OUT_PATH)
            except (OSError, PermissionError):
                # Word or OneDrive might have the file locked during save
                continue
    except KeyboardInterrupt:
        print("\nSaliendo...")
