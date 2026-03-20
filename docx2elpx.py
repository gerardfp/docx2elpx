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
from dataclasses import dataclass, field
from itertools import count

from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import filedialog
from flask import Flask, send_from_directory, jsonify, send_file
from flask_cors import CORS
import logging
import sys

# Silence Flask logging
import flask.cli
flask.cli.show_server_banner = lambda *args: None
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# --- GLOBALS ---
LAST_UPDATE = time.time()

# --- CONFIGURATION & PATHS ---
def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller. PyInstaller creates a temp folder and stores path in _MEIPASS"""
    try: base_path = Path(sys._MEIPASS)
    except Exception: base_path = Path(__file__).resolve().parent
    return base_path / relative_path

TEMPLATE_DIR = resource_path("template")
CURRENT_OUT_PATH = None

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

LANGUAGE_MAP = {
    "valencià": "va", "valenciano": "va", "catalán": "ca", "català": "ca",
    "castellano": "es", "español": "es", "spanish": "es",
    "english": "en", "inglés": "en", "anglès": "en",
}

def slugify(text): return re.sub(r'[-\s]+', '-', re.sub(r'[^\w\s-]', '', normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()).strip())
def generate_id(): return f"{datetime.now().strftime('%Y%m%d%H%M%S')}{''.join(random.choices(string.ascii_uppercase, k=6))}"

@dataclass
class Section:
    block_id: str
    component_id: str
    title: str
    content: str = ""
    metadata: list = field(default_factory=list) # [{"label": str, "value": str}]
    soup: any = None

class SlugRegistry:
    def __init__(self, reserved=None):
        self.used = set()
        self.reserved = reserved or set()

    def generate(self, text):
        base = slugify(text)
        for i in count(0):
            slug = base if i == 0 else f"{base}-{i}"
            if slug not in self.used and (not self.used or slug not in self.reserved):
                self.used.add(slug)
                return slug

@dataclass
class Page:
    title: str
    level: int = 1
    slug: str = ""
    filename: str = ""
    id: str = field(default_factory=generate_id)
    sections: list[Section] = field(default_factory=list)
    children: list["Page"] = field(default_factory=list)
    parent: "Page | None" = None

    def _current_section(self):
        if not self.sections:
            self.add_section("")
        return self.sections[-1]

    def add_section(self, title):
        self.sections.append(Section(block_id=generate_id(), component_id=generate_id(), title=title))

    def add_content(self, html_str):
        self._current_section().content += html_str

    def add_metadata(self, key, value):
        self._current_section().metadata.append({"label": key, "value": value})

def extract_theme_name(theme_path):
    """Extracts theme name from config.xml in the theme folder."""
    config_path = theme_path / "config.xml"
    if not config_path.exists():
        return theme_path.name
    try:
        name_tag = BeautifulSoup(config_path.read_text(encoding="utf-8"), "xml").find("name")
        if name_tag:
            return name_tag.get_text().strip()
    except Exception:
        pass
    return theme_path.name

def process_links(soup, input_dir, output_root, section):
    """Processes links and YouTube embeds in-place on a BeautifulSoup object."""
    section_id = section.component_id
    for a in soup.find_all('a', href=True):
        href = a['href']
        yt_match = re.search(r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]+))', href)
        if yt_match:
            video_id = yt_match.group(2)
            video_container = soup.new_tag("div", **{"class": "exe-video-wrapper exe-video-center exe-video-fixed", "style": "width:560px;"})
            iframe = soup.new_tag("iframe", **{
                "width": "560", "height": "315", "src": f"https://www.youtube.com/embed/{yt_match.group(2)}",
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
    """Wraps images in lightbox anchors where applicable."""
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
                next_img.wrap(soup.new_tag("a", href=next_img['src'], rel="lightbox", id=f"link_{link_counter}"))
                link_counter += 1

            # Add <p class="clearfix"></p> after the lightbox wrapper's parent <p>
            if next_img.find_parent("p"):
                next_img.find_parent("p").insert_after(soup.new_tag("p", **{"class": "clearfix"}))

    return soup

def process_content_resources(soup, output_root, section):
    """Moves images from temp_media to section-specific folders and updates references."""
    section_id = section.component_id
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
        original_name = f"{os.path.splitext(file_name)[0]}_1{os.path.splitext(file_name)[1]}"
        resource_folder.mkdir(parents=True, exist_ok=True)
        src_file = resource_folder / file_name
        dst_file = resource_folder / original_name
        if src_file.exists() and not dst_file.exists():
            shutil.copy2(src_file, dst_file)
        
        file_size_str = f"{dst_file.stat().st_size / 1024:.2f} KB" if dst_file.exists() else ""
        
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
    """Fast parsing of HTML fragments without adding html/body tags."""
    soup = BeautifulSoup(html_str, "lxml")
    if soup.body:
        # Return a new soup containing only the body contents
        new_soup = BeautifulSoup("", "lxml")
        for content in soup.body.contents:
            new_soup.append(copy.deepcopy(content))
        return new_soup
    return soup

def extract_pages_from_docx(docx_path, input_dir, output_root):
    """Extracts content from docx. Uses a temp copy to bypass Word locks."""
    temp_docx = output_root / "temp_watch.docx"
    max_retries = 5
    last_err = None

class ParserContext:
    def __init__(self, soup, input_dir, output_root):
        self.soup = soup
        self.input_dir = input_dir
        self.output_root = output_root
        self.pages = []
        self.current_page = None
        self.section_elements = []
        self.doc_metadata = {}
        self.collecting_description = False
        self.collecting_fx = False
        self.fx_elements = []
        self.current_fx_class = "exe-accordion"
        self.slug_registry = SlugRegistry({"index", "portada"})
        self.is_default_page_active = True

def load_docx_html(docx_path, output_root):
    """Copies DOCX to temp, extracts images, and converts to HTML using Mammoth."""
    temp_docx = output_root / "temp_watch.docx"
    images_folder = output_root / "content" / "resources" / "temp_media"
    images_folder.mkdir(parents=True, exist_ok=True)
    
    last_err = None
    for _ in range(5):
        try:
            shutil.copy2(docx_path, temp_docx)
            break
        except Exception as e:
            last_err = e
            time.sleep(0.5)
    else:
        raise RuntimeError(f"No se pudo leer {docx_path}: {last_err}")

    docx_dims = extract_docx_image_dimensions(temp_docx)
    image_count = 0

    def convert_image(image):
        nonlocal image_count
        image_count += 1
        ext = image.content_type.partition("/")[2]
        file_name = f"image_{image_count}.{ext}"
        with image.open() as img_bytes, open(images_folder / file_name, "wb") as f:
            f.write(img_bytes.read())
        
        img_attrs = {"src": f"{{REL_PREFIX}}content/resources/temp_media/{file_name}"}
        if image_count <= len(docx_dims):
            w, h = docx_dims[image_count - 1]
            img_attrs.update({"width": str(w), "height": str(h)})
        return img_attrs

    try:
        with open(temp_docx, "rb") as f:
            return mammoth.convert_to_html(f, convert_image=mammoth.images.img_element(convert_image)).value
    finally:
        temp_docx.unlink(missing_ok=True)

def flush_section(ctx):
    """Finalizes the current section by processing resources and links."""
    if not ctx.current_page or not ctx.section_elements:
        return

    section_soup = BeautifulSoup("", "lxml")
    for el in ctx.section_elements:
        section_soup.append(copy.deepcopy(el))

    section = ctx.current_page._current_section()
    process_content_resources(section_soup, ctx.output_root, section)
    process_links(section_soup, ctx.input_dir, ctx.output_root, section)
    ctx.current_page.add_content(str(section_soup))
    ctx.section_elements.clear()

def handle_page(ctx, match):
    """Processes a page marker (#)."""
    if ctx.is_default_page_active and not any(s.content for s in ctx.pages[0].sections) and not ctx.section_elements:
        ctx.pages.pop(0)

    flush_section(ctx)
    ctx.is_default_page_active = False
    new_page = Page(title=match.group(2).strip(), level=len(match.group(1)))
    new_page.slug = ctx.slug_registry.generate(new_page.title)
    new_page.filename = "index.html" if new_page.slug in {"index", "portada"} or not ctx.pages else f"{new_page.slug}.html"
    ctx.pages.append(new_page)
    ctx.current_page = new_page

def handle_section(ctx, match):
    """Processes a section marker (%)."""
    flush_section(ctx)
    if ctx.current_page:
        ctx.current_page.add_section(match.group(1).strip())

def handle_metadata(ctx, key, value):
    """Processes a metadata tag ({key: value})."""
    prop_key = DOC_METADATA_KEYS.get(key.lower())
    if prop_key and not ctx.is_default_page_active: # Logic changed: if we haven't found a real page yet, it's doc metadata
        pass # Wait, actual logic was: if not current_page (but we always have a default page)

    # Simplified logic: if no real page marker found, it's document metadata
    if ctx.is_default_page_active:
        if prop_key == "pp_lang":
            value = LANGUAGE_MAP.get(value.lower(), value)
        if prop_key: ctx.doc_metadata[prop_key] = value
    elif ctx.current_page:
        ctx.current_page.add_metadata(key, value)

def parse_elements(ctx):
    """Iterates through elements and dispatches to handlers."""
    page_re = re.compile(r"^(#+)\s*(.+)$")
    section_re = re.compile(r"^%\s*(.+)$")
    metadata_re = re.compile(r"^\{(.+?):\s*(.+?)\}$")
    fx_start_re = re.compile(r"\{(acorde[oó]n|pesta[ñn]as|paginaci[oó]n?|carrusel)\}", re.I)
    fx_map = {"acordeon": "exe-accordion", "pestañas": "exe-tabs", "pestanas": "exe-tabs", "paginacion": "exe-paginated", "paginacio": "exe-paginated", "carrusel": "exe-carousel"}

    elements = ctx.soup.body.contents if ctx.soup.body else ctx.soup.contents
    for el in elements:
        if not el.name:
            (ctx.fx_elements if ctx.collecting_fx else ctx.section_elements).append(el)
            continue
            
        text = el.get_text().strip()
        if ctx.collecting_fx:
            if re.search(r"\{fin(\s+\w+)?\}", text, re.I):
                fx_div = ctx.soup.new_tag("div", attrs={"class": f"exe-fx {ctx.current_fx_class}"})
                for acc_el in ctx.fx_elements:
                    if acc_el.name and (acc_el.name.startswith("h") or acc_el.name == "p") and re.match(r"^>\s*>\s*.+", acc_el.get_text().strip()):
                        h2 = ctx.soup.new_tag("h2")
                        h2.string = re.sub(r"^>\s*>\s*", "", acc_el.get_text().strip()).strip()
                        fx_div.append(h2)
                    else:
                        fx_div.append(copy.deepcopy(acc_el))
                ctx.section_elements.append(fx_div)
                ctx.collecting_fx = False
                ctx.fx_elements.clear()
            else:
                ctx.fx_elements.append(el)
            continue

        fx_match = fx_start_re.search(text)
        if fx_match:
            norm_key = normalize('NFKD', fx_match.group(1).lower()).encode('ASCII', 'ignore').decode('ASCII')
            ctx.current_fx_class = fx_map.get(norm_key, "exe-accordion")
            ctx.collecting_fx = True
            ctx.fx_elements = []
            continue

        if m := page_re.match(text):
            handle_page(ctx, m)
            continue
        if m := section_re.match(text):
            handle_section(ctx, m)
            continue
        if m := metadata_re.match(text):
            handle_metadata(ctx, m.group(1).strip(), m.group(2).strip())
            continue

        if ctx.current_page:
            ctx.section_elements.append(el)

    flush_section(ctx)

def extract_pages_from_docx(docx_path, input_dir, output_root):
    """Main extraction coordinator."""
    soup = BeautifulSoup(load_docx_html(docx_path, output_root), "lxml")
    process_lightboxes(soup)
    
    ctx = ParserContext(soup, input_dir, output_root)
    # Default page
    default_page = Page(title="Portada", level=1)
    default_page.slug = ctx.slug_registry.generate(default_page.title)
    default_page.filename = "index.html"
    ctx.pages.append(default_page)
    ctx.current_page = default_page
    
    parse_elements(ctx)
    
    # Final cleanup of temp image folder
    temp_media = output_root / "content" / "resources" / "temp_media"
    if temp_media.exists():
        try: shutil.rmtree(temp_media)
        except: pass

    return build_hierarchy(ctx.pages), ctx.doc_metadata

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
    
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<ode xmlns="http://www.intef.es/xsd/ode" version="2.0">
    <userPreferences>
        <userPreference><key>theme</key><value>{html.escape(theme_name)}</value></userPreference>
    </userPreferences>
    <odeResources>
        <odeResource><key>odeVersionId</key><value>{generate_id()}</value></odeResource>
        <odeResource><key>odeId</key><value>{generate_id()}</value></odeResource>
        <odeResource><key>odeVersionName</key><value>0</value></odeResource>
        <odeResource><key>isDownload</key><value>true</value></odeResource>
        <odeResource><key>eXeVersion</key><value>v3.0.2</value></odeResource>
    </odeResources>
    <odeProperties>
        <odeProperty><key>pp_title</key><value>{html.escape(doc_metadata.get("pp_title", package_title))}</value></odeProperty>
        <odeProperty><key>pp_subtitle</key><value>{html.escape(doc_metadata.get("pp_subtitle", ""))}</value></odeProperty>
        <odeProperty><key>pp_lang</key><value>{html.escape(doc_metadata.get("pp_lang", "va"))}</value></odeProperty>
        <odeProperty><key>pp_author</key><value>{html.escape(doc_metadata.get("pp_author", "Autor del recurs"))}</value></odeProperty>
        <odeProperty><key>license</key><value>{html.escape(doc_metadata.get("license", "creative commons: attribution - share alike 4.0"))}</value></odeProperty>
        <odeProperty><key>pp_description</key><value>{html.escape(doc_metadata.get("pp_description", description))}</value></odeProperty>
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
            icon = "objectives" if any(k in (section.title or "").lower() for k in ["reto", "objetivos", "mision"]) else ""
            
            # Prepare content for XML: transform resource paths to {{context_path}}
            xml_content = section.content.replace("{REL_PREFIX}content/resources/", f"{{{{context_path}}}}/")
            xml_content = xml_content.replace(f"content/resources/{section.component_id}/", f"{{{{context_path}}}}/{section.component_id}/")

            # Build metadata <dl> block if present
            dl_block = ""
            if section.metadata:
                dl_items = ""
                for item in section.metadata:
                    label = html.escape(item["label"])
                    value = html.escape(item["value"])
                    dl_items += f'<div class="inline"><dt><span title="{label}">{label}</span></dt><dd>{value}</dd></div>'
                dl_block = f'<dl>{dl_items}</dl>'

            # Build metadata map for JSON compatibility
            metadata_map = {item["label"].lower(): item["value"] for item in section.metadata}
            json_props = {
                "ideviceId": section.component_id,
                "textTextarea": xml_content,
                "textFeedbackInput": "Mostra la retroacció",
                "textFeedbackTextarea": ""
            }
            if section.metadata:
                json_props["textInfoDurationInput"] = section.metadata[0]["value"]
                json_props["textInfoDurationTextInput"] = section.metadata[0]["label"]
            if len(section.metadata) > 1:
                json_props["textInfoParticipantsInput"] = section.metadata[1]["value"]
                json_props["textInfoParticipantsTextInput"] = section.metadata[1]["label"]

            xml += f"""                <odePagStructure>
                    <odePageId>{page.id}</odePageId>
                    <odeBlockId>{section.block_id}</odeBlockId>
                    <blockName>{html.escape(section.title) if section.title else " "}</blockName>
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
                            <odeBlockId>{section.block_id}</odeBlockId>
                            <odeIdeviceId>{section.component_id}</odeIdeviceId>
                            <odeIdeviceTypeName>text</odeIdeviceTypeName>
                            <htmlView>{html.escape(f'<div class="exe-text-template"><div class="textIdeviceContent"><div class="exe-text-activity"><div>{dl_block}{xml_content}</div></div></div></div>')}</htmlView>
                            <jsonProperties>{html.escape(json.dumps(json_props))}</jsonProperties>
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
    if theme_path and theme_path.is_dir():
        shutil.copytree(theme_path, output_root / "theme", dirs_exist_ok=True)

    soup_template = BeautifulSoup((TEMPLATE_DIR / "index.html").read_text(encoding="utf-8"), "lxml")
    
    package_title_tag = soup_template.find("h1", class_="package-title")
    if doc_metadata and "pp_title" in doc_metadata:
        package_title = doc_metadata["pp_title"]
        if package_title_tag: package_title_tag.string = package_title
    else:
        package_title = package_title_tag.get_text() if package_title_tag else "Proyecto eXeLearning"

    if soup_template.head:
        soup_template.head.append(soup_template.new_tag("link", rel="stylesheet", **{"type": "text/css", "href": "{REL_PREFIX}libs/exe_lightbox/exe_lightbox.css"}))
        soup_template.head.append(soup_template.new_tag("script", **{"type": "text/javascript", "src": "{REL_PREFIX}libs/exe_lightbox/exe_lightbox.js"}))

    for page in pages:
        for section in page.sections:
            section.soup = parse_html_fragment(section.content)

    reload_script_soup = parse_html_fragment(f"""
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
    """)

    write_tasks = []
    for page in pages:
        page_soup = copy.deepcopy(soup_template)
        if page_soup.title: page_soup.title.string = f"{page.title} | {package_title}"
        if page_soup.find("h2", class_="page-title"): page_soup.find("h2", class_="page-title").string = page.title
            
        nav_placeholder = page_soup.find("nav", id="siteNav")
        content_placeholder = page_soup.find("div", class_="page-content")
        
        if content_placeholder:
            for article in content_placeholder.find_all("article"): article.decompose()
            for section in page.sections:
                article_tag = page_soup.new_tag("article", **{"class": "box" if section.title else "box no-header", "id": section.block_id})
                if section.title:
                    head = page_soup.new_tag("header", **{"class": "box-head"})
                    icon_div = page_soup.new_tag("div", **{"class": "box-icon exe-icon"})
                    icon_div.append(page_soup.new_tag("img", **{"src": f"theme/icons/{'objectives.png' if any(k in section.title.lower() for k in ['reto', 'objetivos', 'mision']) else 'reading.png' if any(k in section.title.lower() for k in ['lectura', 'texto', 'leer']) else 'draw.png'}", "alt": ""}))
                    head.append(icon_div)
                    
                    title_h1 = page_soup.new_tag("h1", **{"class": "box-title"})
                    title_h1.string = section.title
                    head.append(title_h1)
                    
                    toggle_btn = page_soup.new_tag("button", **{"class": "box-toggle box-toggle-on", "title": "Ocultar/Mostrar contenido"})
                    toggle_btn.append(page_soup.new_tag("span", string="Ocultar/Mostrar contenido"))
                    head.append(toggle_btn)
                    article_tag.append(head)
                
                box_content = page_soup.new_tag("div", **{"class": "box-content"})
                idevice_node = page_soup.new_tag("div", **{"id": section.component_id, "class": "idevice_node text loaded", "data-idevice-path": "idevices/text/", "data-idevice-type": "text", "data-idevice-component-type": "json"})
                inner_template = page_soup.new_tag("div", **{"class": "exe-text-template"})
                text_content = page_soup.new_tag("div", **{"class": "textIdeviceContent"})
                activity_wrapper = page_soup.new_tag("div", **{"class": "exe-text-activity"})
                inner_div = page_soup.new_tag("div")
                inner_div.extend(copy.deepcopy(section.soup).contents)
                activity_wrapper.append(inner_div)
                text_content.append(activity_wrapper)
                inner_template.append(text_content)
                idevice_node.append(inner_template)
                box_content.append(idevice_node)
                article_tag.append(box_content)
                content_placeholder.append(article_tag)

        prefix = "" if page.filename == "index.html" else "../"
        for tag in page_soup.find_all(["link", "script", "img", "a"], recursive=True):
            for attr in ["href", "src"]:
                if tag.has_attr(attr):
                    val = tag[attr]
                    if "{REL_PREFIX}" in val:
                        tag[attr] = val.replace("{REL_PREFIX}", prefix)
                    elif page.filename != "index.html" and not val.startswith(("http", "https", "#", "data:", "/")):
                        tag[attr] = prefix + val

        if nav_placeholder:
            page_nav_html = generate_site_nav(pages).replace(f"[[ACTIVE_{page.id}]]", "active").replace("{REL_PREFIX}", prefix)
            page_nav_html = re.sub(r"\[\[ACTIVE_[\w-]+\]\]", "", page_nav_html)
            nav_soup = BeautifulSoup(page_nav_html, "lxml")
            nav_placeholder.replace_with(nav_soup.body.next_element if nav_soup.body else nav_soup)

        if page_soup.body:
            page_soup.body.append(copy.deepcopy(reload_script_soup))

        output_path = (output_root if page.filename == "index.html" else output_root / "html") / page.filename
        write_tasks.append((output_path, str(page_soup)))

    write_tasks.append((output_root / "content.xml", generate_content_xml(pages, package_title, soup_template.find("meta", attrs={"name": "description"})["content"] if soup_template.find("meta", attrs={"name": "description"}) else "", doc_metadata, theme_name)))

    # Parallel write
    with ThreadPoolExecutor() as executor:
        for path, content in write_tasks:
            executor.submit(write_file, path, content)

def prepare_output(output_root):
    """Initializes output directory with template assets."""
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "html").mkdir(exist_ok=True)
    for folder in ["libs", "theme", "idevices", "content", "custom"]:
        shutil.copytree(TEMPLATE_DIR / folder, output_root / folder, dirs_exist_ok=True)

def run_conversion(docx_path, input_dir, output_root):
    """Full conversion flow. Optimized and instrumented."""
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
        # 4. ONLY NOW update the global status so the browser reloads
        global LAST_UPDATE
        LAST_UPDATE = target_update
        
        print(f"✅ Conversión completada en {time.time() - start_time:.2f}s (Ext: {t_extract:.2f}s, Pkg: {time.time() - t0:.2f}s)")
    except Exception as e:
        print(f"❌ Error en conversión: {e}")
        import traceback
        traceback.print_exc()

# --- WEB SERVER ---
app = Flask(__name__)
CORS(app)

@app.route("/")
def serve_index():
    return send_from_directory(CURRENT_OUT_PATH.resolve(), "index.html")

@app.route("/html/<path:path>")
def serve_html(path):
    return send_from_directory((CURRENT_OUT_PATH / "html").resolve(), path)

@app.route("/status")
def get_status():
    return jsonify({"last_update": int(LAST_UPDATE * 1000)})

@app.route("/elpx")
def download_elpx():
    """Zips the output directory and serves it as a .elpx file."""     
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
    return send_file(memory_file, mimetype='application/zip', as_attachment=True, download_name=f"{CURRENT_OUT_PATH.parent.name}.elpx")

@app.route("/<path:path>")
def serve_static(path):
    full_path = CURRENT_OUT_PATH / path
    if full_path.exists():
        return send_from_directory(CURRENT_OUT_PATH.resolve(), path)
    return "Not Found", 404

def start_flask():
    app.run(host="127.0.0.1", port=5500, debug=False, use_reloader=False)

if __name__ == "__main__":
    # 1. Select Folder
    root = tk.Tk()
    root.withdraw()
    folder_selected = filedialog.askdirectory(title="Selecciona la carpeta que contiene exelearning.docx")
    root.destroy()
    
    if not folder_selected:
        print("No se seleccionó ninguna carpeta. Saliendo.")
        exit()

    base_path = Path(folder_selected).resolve()
    docx_files = [f for f in base_path.glob("*.docx") if not f.name.startswith("~$")]    
    if not docx_files:
        print(f"Error: No se encontró ningún archivo .docx en {base_path}")
        exit()

    docx_file = docx_files[0]
    CURRENT_OUT_PATH = base_path / "output"
    print(f"📁 Directorio de trabajo: {base_path}")
    print(f"📄 Archivo DOCX detectado: {docx_file.name}")

    # 2. Initial Conversion
    prepare_output(CURRENT_OUT_PATH)
    run_conversion(docx_file, base_path, CURRENT_OUT_PATH)

    # 3. Start Server in Thread
    threading.Thread(target=start_flask, daemon=True).start()
    print(f"\n🔥 Servidor en vivo: http://localhost:5500")

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
                    print(f"\n📝 Cambio detectado en {docx_file.name}")
                    run_conversion(docx_file, base_path, CURRENT_OUT_PATH)
            except (OSError, PermissionError):
                # Word or OneDrive might have the file locked during save
                continue
    except KeyboardInterrupt:
        print("\nSaliendo...")
