import markdown
import yaml
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
    """Get absolute path to resource, works for dev and for PyInstaller."""
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

def slugify(text): 
    return re.sub(r'[-\s]+', '-', re.sub(r'[^\w\s-]', '', normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()).strip())

def generate_id(): 
    return f"{datetime.now().strftime('%Y%m%d%H%M%S')}{''.join(random.choices(string.ascii_uppercase, k=6))}"

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
            embed_url = f"https://www.youtube.com/embed/{video_id}"
            parent_p = a.find_parent('p')
            style = parent_p.get("style", "") if parent_p else ""
            is_centered = parent_p and "text-align: center" in style
            
            if is_centered:
                span_src = soup.new_tag("span", **{"class": "external-iframe-src", "style": "display:none"})
                a_src = soup.new_tag("a", href=embed_url)
                a_src.string = embed_url
                span_src.append(a_src)
                
                iframe = soup.new_tag("iframe", **{
                    "width": "560", "height": "314", "src": embed_url,
                    "allowfullscreen": "allowfullscreen", "class": "external-iframe"
                })
                
                new_p = soup.new_tag("p", style=style)
                new_p.append(span_src)
                new_p.append(iframe)
                
                if parent_p:
                    if parent_p.get_text(strip=True) != a.get_text(strip=True):
                        parent_p.insert_after(new_p)
                        a.extract()
                    else:
                        parent_p.replace_with(new_p)
                else:
                    a.replace_with(new_p)
            else:
                video_container = soup.new_tag("div", **{"class": "exe-video-wrapper exe-video-center exe-video-fixed", "style": "width:560px;"})
                iframe = soup.new_tag("iframe", **{
                    "width": "560", "height": "315", "src": embed_url,
                    "frameborder": "0", "allowfullscreen": "allowfullscreen"
                })
                video_container.append(iframe)
                a.replace_with(video_container)
            continue
            
        # Local Files
        if not href.startswith(("http://", "https://", "data:", "//", "{REL_PREFIX}")):
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

def parse_markdown_link(text):
    """Parses 'Text [URL]' into (text, url)."""
    match = re.search(r"^(.*?)\s*\[(https?://.*?)\]$", text.strip())
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return text.strip(), None

def process_figures(soup):
    """Processes images followed by front-matter style YAML metadata into eXeLearning figures."""
    for img in soup.find_all("img"):
        parent = img.parent
        if not parent:
            continue
            
        # Check if parent is a single-element wrapper for the image
        is_wrapper = parent.name in ["p", "h1", "h2", "h3", "h4", "h5", "h6", "div"]
        if is_wrapper:
            other_elements = [c for c in parent.contents if c != img and (not isinstance(c, str) or c.strip())]
            is_single_wrapper = len(other_elements) == 0
        else:
            is_single_wrapper = False
            
        start_el = parent if is_single_wrapper else img
        
        # Get next tag siblings
        siblings = []
        curr = start_el.next_sibling
        while curr:
            if curr.name: # Tag
                siblings.append(curr)
            elif isinstance(curr, str) and curr.strip():
                # Non-empty string sibling - stop search here
                break
            curr = curr.next_sibling
            
        if not siblings:
            continue
            
        meta_p = None
        to_remove = []
        
        # Case A: sib0 is hr, sib1 is p, sib2 is hr
        if len(siblings) >= 2 and siblings[0].name == "hr" and siblings[1].name == "p":
            content = siblings[1].get_text()
            valid_keys = ["titulo", "título", "autor", "alt", "pie", "ancho", "alto"]
            if any(f"{key}:" in content.lower() for key in valid_keys):
                meta_p = siblings[1]
                to_remove.append(siblings[0])
                to_remove.append(siblings[1])
                if len(siblings) >= 3 and siblings[2].name == "hr":
                    to_remove.append(siblings[2])
                    
        # Case B: sib0 is p, sib1 is hr (or just sib0 is p)
        elif siblings[0].name == "p":
            content = siblings[0].get_text()
            valid_keys = ["titulo", "título", "autor", "alt", "pie", "ancho", "alto"]
            if any(f"{key}:" in content.lower() for key in valid_keys):
                meta_p = siblings[0]
                to_remove.append(siblings[0])
                if len(siblings) >= 2 and siblings[1].name == "hr":
                    to_remove.append(siblings[1])
                    
        if not meta_p:
            continue
            
        # Extract fields
        content = meta_p.get_text()
        def get_field(key, pattern=r"(.*?)$"):
            m = re.search(fr"{key}:\s*{pattern}", content, re.I | re.M)
            return m.group(1).strip() if m else None

        title_raw = get_field("título") or get_field("titulo")
        author_raw = get_field("autor")
        alt_raw = get_field("alt")
        caption_raw = get_field("pie")
        width = get_field("ancho", r"(\d+)")
        height = get_field("alto", r"(\d+)")

        title_text, title_url = parse_markdown_link(title_raw) if title_raw else (None, None)
        author_text, author_url = parse_markdown_link(author_raw) if author_raw else (None, None)
        caption_text, caption_url = parse_markdown_link(caption_raw) if caption_raw else (None, None)

        figure = soup.new_tag("figure", attrs={"class": "exe-figure position-center"})
        if width:
            figure["style"] = f"width: {width}px;"

        if title_text:
            header_div = soup.new_tag("div", attrs={"class": "figcaption header"})
            strong = soup.new_tag("strong")
            strong.string = title_text
            header_div.append(strong)
            figure.append(header_div)

        new_img = copy.deepcopy(img)
        if width: new_img["width"] = width
        if height: new_img["height"] = height
        if alt_raw: new_img["alt"] = alt_raw
        if title_text: new_img["title"] = title_text
        figure.append(new_img)

        figcaption = soup.new_tag("figcaption", attrs={"class": "figcaption"})
        
        if author_text:
            if author_url:
                author_a = soup.new_tag("a", href=author_url, attrs={"class": "author", "target": "_blank", "rel": "noopener"})
                author_a.string = author_text
                figcaption.append(author_a)
            else:
                span_author = soup.new_tag("span", attrs={"class": "author"})
                span_author.string = author_text
                figcaption.append(span_author)
            figcaption.append(". ")

        if caption_text:
            if caption_url:
                caption_a = soup.new_tag("a", href=caption_url, attrs={"class": "title", "target": "_blank", "rel": "noopener"})
                em = soup.new_tag("em")
                em.string = caption_text
                caption_a.append(em)
                figcaption.append(caption_a)
            else:
                em = soup.new_tag("em")
                em.string = caption_text
                figcaption.append(em)
            figcaption.append(" ")

        license_span = soup.new_tag("span", attrs={"class": "license"})
        sep1 = soup.new_tag("span", attrs={"class": "sep"})
        sep1.string = "("
        license_span.append(sep1)
        
        license_a = soup.new_tag("a", href="http://creativecommons.org/licenses/", attrs={"class": "license", "target": "_blank", "rel": "noopener"})
        license_a.string = "CC BY"
        license_span.append(license_a)
        
        sep2 = soup.new_tag("span", attrs={"class": "sep"})
        sep2.string = ")"
        license_span.append(sep2)
        
        figcaption.append(license_span)
        figure.append(figcaption)

        # Remove metadata tags and horizontal rules from HTML
        for el in to_remove:
            el.extract()

        # Replace single-wrapper parent or the image itself
        if is_single_wrapper:
            start_el.replace_with(figure)
        else:
            img.replace_with(figure)

    return soup

def process_lightboxes(soup):
    """Wraps images in lightbox anchors where applicable."""
    link_counter = 0
    for text_node in soup.find_all(string=re.compile(r"\{lightbox\}")):
        parent = text_node.parent
        new_text = text_node.replace("{lightbox}", "").strip()
        if not new_text:
            text_node.extract()
        else:
            text_node.replace_with(new_text)

        next_img = parent.find_next("img")
        if next_img:
            if not next_img.get('alt'):
                next_img['alt'] = ""

            current = next_img.parent
            is_wrapped = False
            while current and current.name != 'body':
                if current.name == 'a':
                    is_wrapped = True
                    if not current.get('rel'):
                        current['rel'] = "lightbox"
                    elif "lightbox" not in current['rel']:
                        current['rel'] = f"{current['rel']} lightbox".strip()
                    current['id'] = f"link_{link_counter}"
                    link_counter += 1
                    break
                current = current.parent
            
            if not is_wrapped:
                next_img.wrap(soup.new_tag("a", href=next_img['src'], rel="lightbox", id=f"link_{link_counter}"))
                link_counter += 1

            if next_img.find_parent("p"):
                next_img.find_parent("p").insert_after(soup.new_tag("p", **{"class": "clearfix"}))

    return soup

def process_content_resources(soup, input_dir, output_root, section):
    """Moves local images and resources to section-specific folders and updates references."""
    section_id = section.component_id
    resource_folder = output_root / "content" / "resources" / section_id
    
    # 1. Process <img> tags
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src and not src.startswith(("http://", "https://", "data:", "//", "{REL_PREFIX}")):
            file_name = Path(src).name
            local_file_path = input_dir / file_name
            if local_file_path.exists() and local_file_path.is_file():
                resource_folder.mkdir(parents=True, exist_ok=True)
                shutil.copy2(local_file_path, resource_folder / file_name)
                img["src"] = f"{{REL_PREFIX}}content/resources/{section_id}/{file_name}"

    # 2. Process lightbox links (<a> tags with rel="lightbox")
    for a in soup.find_all("a", rel=re.compile(r"lightbox")):
        href = a.get("href", "")
        if href and not href.startswith(("http://", "https://", "data:", "//", "{REL_PREFIX}")):
            file_name = Path(href).name
            local_file_path = input_dir / file_name
            if local_file_path.exists() and local_file_path.is_file():
                resource_folder.mkdir(parents=True, exist_ok=True)
                shutil.copy2(local_file_path, resource_folder / file_name)
        elif f"content/resources/{section_id}/" in href:
            file_name = href.split("/")[-1]
        else:
            continue

        original_name = f"{os.path.splitext(file_name)[0]}_1{os.path.splitext(file_name)[1]}"
        resource_folder.mkdir(parents=True, exist_ok=True)
        src_file = resource_folder / file_name
        dst_file = resource_folder / original_name
        if src_file.exists() and not dst_file.exists():
            shutil.copy2(src_file, dst_file)
        
        file_size_str = f"{dst_file.stat().st_size / 1024:.2f} KB" if dst_file.exists() else ""
        
        a["href"] = f"{{REL_PREFIX}}content/resources/{section_id}/{original_name}"
        a["title"] = original_name
        a["size"] = file_size_str
        
        img_tag = a.find("img")
        if img_tag:
            img_tag["src"] = f"{{REL_PREFIX}}content/resources/{section_id}/{file_name}"

    return soup

def compile_markdown_to_html(md_text):
    """Compiles Markdown text to HTML with support for GFM tables, codehilite, etc."""
    return markdown.markdown(md_text, extensions=['extra'])

def parse_html_fragment(html_str):
    soup = BeautifulSoup(html_str, "lxml")
    if soup.body:
        new_soup = BeautifulSoup("", "lxml")
        for content in soup.body.contents:
            new_soup.append(copy.deepcopy(content))
        return new_soup
    return soup

def extract_pages_from_markdown(md_path, input_dir, output_root):
    """Parses exemark (.md) file into Page and Section structures."""
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Parse YAML Front Matter
    doc_metadata = {}
    md_content = content
    if content.startswith("---"):
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if match:
            yaml_block = match.group(1)
            md_content = content[match.end():]
            try:
                raw_meta = yaml.safe_load(yaml_block)
                if isinstance(raw_meta, dict):
                    for k, v in raw_meta.items():
                        doc_metadata[k.lower()] = str(v)
            except Exception as e:
                print(f"[Warning] Error parsing front matter: {e}")

    mapped_metadata = {}
    for key, val in doc_metadata.items():
        prop_key = DOC_METADATA_KEYS.get(key)
        if prop_key:
            if prop_key == "pp_lang":
                val = LANGUAGE_MAP.get(val.lower(), val)
            mapped_metadata[prop_key] = val

    # 2. Parse exemark lines
    pages = []
    slug_registry = SlugRegistry({"index", "portada"})
    lines = md_content.splitlines()
    
    current_page = None
    current_section = None
    
    # Regex definitions matching double-hash pages
    page_re = re.compile(r"^(#+)\s+\1\s+(.+)$")
    section_re = re.compile(r"^>\s*(.+)$")
    block_meta_re = re.compile(r"^\{(.+?):\s*(.+?)\}$")
    fx_start_re = re.compile(r"^:::(acorde[oó]n|pesta[ñn]as|paginaci[oó]n?|carrusel)\s*$", re.I)
    container_end_re = re.compile(r"^:::\s*$")
    lightbox_start_re = re.compile(r"^:::lightbox\s*$", re.I)
    
    in_fx = False
    fx_type = None
    fx_panes = []
    current_pane = None
    
    in_lightbox = False
    lightbox_lines = []

    def flush_section_md(sect):
        if sect and hasattr(sect, "md_lines") and sect.md_lines:
            md_str = "\n".join(sect.md_lines)
            html_str = compile_markdown_to_html(md_str)
            sect.content += html_str
            sect.md_lines = []

    def add_page(title, level):
        nonlocal current_page, current_section
        flush_section_md(current_section)
        new_page = Page(title=title, level=level)
        new_page.slug = slug_registry.generate(new_page.title)
        new_page.filename = "index.html" if new_page.slug in {"index", "portada"} or not pages else f"{new_page.slug}.html"
        pages.append(new_page)
        current_page = new_page
        current_section = None
        
    def add_section(title):
        nonlocal current_section
        flush_section_md(current_section)
        if not current_page:
            add_page("Portada", 1)
        current_page.add_section(title)
        current_section = current_page.sections[-1]
        current_section.md_lines = []

    idx = 0
    prev_line_starts_with_gt = False
    
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        
        # A. Handle FX container state
        if in_fx:
            prev_line_starts_with_gt = False
            if container_end_re.match(stripped):
                in_fx = False
                fx_html = f'\n<div class="exe-fx {fx_type}">\n'
                for pane in fx_panes:
                    pane_title = pane["title"]
                    pane_md = "\n".join(pane["content_lines"])
                    pane_html = compile_markdown_to_html(pane_md)
                    fx_html += f'  <h2>{html.escape(pane_title)}</h2>\n'
                    fx_html += f'  <div>{pane_html}</div>\n'
                fx_html += '</div>\n'
                
                if not current_section:
                    add_section("")
                current_section.content += fx_html
                fx_panes = []
                current_pane = None
                idx += 1
                continue
                
            elif stripped.startswith(">>"):
                pane_title = re.sub(r"^>>\s*", "", stripped).strip()
                current_pane = {"title": pane_title, "content_lines": []}
                fx_panes.append(current_pane)
                idx += 1
                continue
            else:
                if current_pane:
                    current_pane["content_lines"].append(line)
                idx += 1
                continue
                
        # B. Handle Lightbox container state
        if in_lightbox:
            prev_line_starts_with_gt = False
            if container_end_re.match(stripped):
                in_lightbox = False
                lightbox_md = "\n".join(lightbox_lines)
                lightbox_html = compile_markdown_to_html(lightbox_md)
                
                # Tag it for BeautifulSoup lightbox wrapping
                lightbox_final_html = f"\n{{lightbox}}\n{lightbox_html}\n"
                
                if not current_section:
                    add_section("")
                current_section.content += lightbox_final_html
                lightbox_lines = []
                idx += 1
                continue
            else:
                lightbox_lines.append(line)
                idx += 1
                continue

        # C. Match exemark blocks
        starts_with_gt = stripped.startswith(">") and not stripped.startswith(">>")
        is_section_header = False
        if starts_with_gt and not prev_line_starts_with_gt:
            text = re.sub(r"^>\s*", "", stripped).strip()
            if text and not text.startswith(('"', "'", "“", "”", "«", "»", "—", "-", "*", "_")) and len(text) < 100 and not ("[" in text and "]" in text):
                is_section_header = True

        if m := page_re.match(stripped):
            prev_line_starts_with_gt = False
            level = len(m.group(1))
            title = m.group(2).strip()
            add_page(title, level)
            idx += 1
            continue
            
        elif is_section_header:
            prev_line_starts_with_gt = False
            title = re.sub(r"^>\s*", "", stripped).strip()
            add_section(title)
            idx += 1
            
            # Check immediately following lines for block metadata
            while idx < len(lines):
                next_stripped = lines[idx].strip()
                if m_meta := block_meta_re.match(next_stripped):
                    k = m_meta.group(1).strip()
                    v = m_meta.group(2).strip()
                    current_section.metadata.append({"label": k, "value": v})
                    idx += 1
                elif not next_stripped:
                    idx += 1
                else:
                    break
            continue
            
        elif m_fx := fx_start_re.match(stripped):
            prev_line_starts_with_gt = False
            flush_section_md(current_section)
            in_fx = True
            norm_key = normalize('NFKD', m_fx.group(1).lower()).encode('ASCII', 'ignore').decode('ASCII')
            fx_map = {"acordeon": "exe-accordion", "pestanas": "exe-tabs", "paginacion": "exe-paginated", "carrusel": "exe-carousel"}
            fx_type = fx_map.get(norm_key, "exe-accordion")
            fx_panes = []
            current_pane = None
            idx += 1
            continue
            
        elif lightbox_start_re.match(stripped):
            prev_line_starts_with_gt = False
            flush_section_md(current_section)
            in_lightbox = True
            lightbox_lines = []
            idx += 1
            continue

        # D. Accumulate standard markdown content lines
        if not current_section:
            add_section("")
            
        current_section.md_lines.append(line)
        prev_line_starts_with_gt = starts_with_gt
        idx += 1

    flush_section_md(current_section)
    
    # 3. Post-process accumulated pages
    # Run BeautifulSoup processors on each section's compiled HTML
    for p in pages:
        for s in p.sections:
            soup = BeautifulSoup(s.content, "lxml")
            
            process_figures(soup)
            process_lightboxes(soup)
            process_content_resources(soup, input_dir, output_root, s)
            process_links(soup, input_dir, output_root, s)
            
            # Unpack body element context
            s.content = "".join(str(c) for c in (soup.body.contents if soup.body else soup.contents))

    return build_hierarchy(pages), mapped_metadata

def build_hierarchy(flat_pages):
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
    roots = [p for p in all_pages if p.parent is None]
    def build_list(nodes):
        if not nodes: return ""
        html_ul = "<ul>\n"
        for node in nodes:
            rel_path = "index.html" if node.filename == "index.html" else f"html/{node.filename}"
            html_ul += f'<li><a href="{{REL_PREFIX}}{rel_path}" class="no-ch [[ACTIVE_{node.id}]]"><span>{node.title}</span></a>'
            if node.children:
                html_ul += build_list(node.children)
            html_ul += "</li>\n"
        html_ul += "</ul>\n"
        return html_ul
    return f'<nav id="siteNav">\n{build_list(roots)}\n</nav>'

def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def generate_content_xml(pages, package_title, description="", doc_metadata=None, theme_name="base"):
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
            xml_content = section.content.replace("{REL_PREFIX}content/resources/", f"{{{{context_path}}}}/")
            xml_content = xml_content.replace(f"content/resources/{section.component_id}/", f"{{{{context_path}}}}/{section.component_id}/")

            dl_block = ""
            if section.metadata:
                dl_items = ""
                for item in section.metadata:
                    label = html.escape(item["label"])
                    value = html.escape(item["value"])
                    dl_items += f'<div class="inline"><dt><span title="{label}">{label}</span></dt><dd>{value}</dd></div>'
                dl_block = f'<dl>{dl_items}</dl>'

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
    """Creates the folder structure and generates all HTML files."""
    if theme_path and theme_path.is_dir():
        shutil.copytree(theme_path, output_root / "theme", dirs_exist_ok=True)

    soup_template = BeautifulSoup((TEMPLATE_DIR / "index.html").read_text(encoding="utf-8"), "lxml")
    
    package_title_tag = soup_template.find("h1", class_="package-title")
    if doc_metadata and "pp_title" in doc_metadata:
        package_title = doc_metadata["pp_title"]
        if package_title_tag: package_title_tag.string = package_title
    else:
        package_title = package_title_tag.get_text() if package_title_tag else "Proyecto eXeLearning"

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
        src_folder = TEMPLATE_DIR / folder
        if src_folder.exists():
            shutil.copytree(src_folder, output_root / folder, dirs_exist_ok=True)
        else:
            (output_root / folder).mkdir(exist_ok=True)

def run_conversion(md_path, input_dir, output_root):
    """Full conversion flow."""
    start_time = time.time()
    try:
        target_update = time.time()
        
        t0 = time.time()
        pages, doc_metadata = extract_pages_from_markdown(md_path, input_dir, output_root)
        t_extract = time.time() - t0
        
        # Detect custom theme
        theme_path = md_path.parent / "theme"
        theme_name = "base"
        if theme_path.is_dir():
            theme_name = extract_theme_name(theme_path)
        
        t0 = time.time()
        create_exelearning_package(pages, output_root, target_update, doc_metadata, theme_path, theme_name)
        
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
                file_path = Path(root) / file
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
    folder_selected = filedialog.askdirectory(title="Selecciona la carpeta que contiene el archivo .md")
    root.destroy()
    
    if not folder_selected:
        print("No se seleccionó ninguna carpeta. Saliendo.")
        exit()

    base_path = Path(folder_selected).resolve()
    
    # Priority: Find md files excluding readme/todo/rules
    md_files = [f for f in base_path.glob("*.md") if f.name.lower() not in ["readme.md", "todo.md", "project_rules.md"]]
    if not md_files:
        md_files = [f for f in base_path.glob("*.md")]
        
    if not md_files:
        print(f"Error: No se encontró ningún archivo .md en {base_path}")
        exit()

    md_file = md_files[0]
    CURRENT_OUT_PATH = base_path / "output"
    print(f"📁 Directorio de trabajo: {base_path}")
    print(f"📄 Archivo MD detectado: {md_file.name}")

    # 2. Initial Conversion
    prepare_output(CURRENT_OUT_PATH)
    run_conversion(md_file, base_path, CURRENT_OUT_PATH)

    # 3. Start Server in Thread
    threading.Thread(target=start_flask, daemon=True).start()
    print(f"\n🔥 Servidor en vivo: http://localhost:5500")

    # 4. Watch Loop
    try:
        last_mtime = md_file.stat().st_mtime
    except:
        last_mtime = 0

    try:
        while True:
            time.sleep(0.5)
            try:
                if not md_file.exists():
                    continue
                current_mtime = md_file.stat().st_mtime
                if current_mtime > last_mtime:
                    last_mtime = current_mtime
                    print(f"\n📝 Cambio detectado en {md_file.name}")
                    run_conversion(md_file, base_path, CURRENT_OUT_PATH)
            except (OSError, PermissionError):
                continue
    except KeyboardInterrupt:
        print("\nSaliendo...")
