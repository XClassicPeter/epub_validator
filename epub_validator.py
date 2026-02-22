#!/usr/bin/env python3
"""
EPUB Validator - Assess EPUB files for compatibility issues across different readers
Supports: Standard PC readers, Apple Books, PocketBook, and Amazon KDP

Version: 1.5
Last Updated: 2026-02-22

See CHANGELOG.md for version history.
"""

import os
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
import re
import struct
from collections import defaultdict


class EPUBValidator:
    """Validates EPUB files and reports platform-specific issues"""
    
    # Security limits
    MAX_UNCOMPRESSED_SIZE = 500 * 1024 * 1024  # 500MB
    MAX_COMPRESSION_RATIO = 100
    
    # Pre-compiled regex patterns for performance
    RE_ID_ATTR = re.compile(r'\bid\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
    RE_HREF_ATTR = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
    RE_SCRIPT_TAG = re.compile(r'<script[>\s]', re.IGNORECASE)
    RE_COMMENT = re.compile(r'<!--.*?-->', re.DOTALL)
    RE_CSS_COMMENT = re.compile(r'/\*.*?\*/', re.DOTALL)
    RE_TRANSFORM = re.compile(r'(?<!text-)transform\s*:', re.IGNORECASE)
    RE_LARGE_MARGIN = re.compile(r'margin[^:]*:\s*(\d+(?:\.\d+)?)(em|rem)', re.IGNORECASE)
    RE_VIEWPORT_UNITS = re.compile(r'\d+vw|\d+vh|\d+vmin|\d+vmax')
    RE_BCP47 = re.compile(r'^[a-zA-Z]{2,3}(-[a-zA-Z]{2,4})?(-[a-zA-Z]{4})?(-[a-zA-Z0-9]{2,8})*$')

    # KDP-specific pre-compiled patterns
    RE_FORM_ELEMENTS = re.compile(r'<(form|input|canvas|iframe)[\s>]', re.IGNORECASE)
    RE_AUDIO_VIDEO_HTML = re.compile(r'<(audio|video)[\s>]', re.IGNORECASE)
    RE_BASE64_IMAGE = re.compile(r'src\s*=\s*["\']data:image/', re.IGNORECASE)
    RE_IMG_ALT = re.compile(r'<img\s[^>]*?/?>', re.IGNORECASE | re.DOTALL)
    RE_CSS_FONT_SIZE_FIXED = re.compile(r'font-size\s*:\s*\d+(?:\.\d+)?\s*(?:px|pt)\b', re.IGNORECASE)
    RE_CSS_NEGATIVE_MARGIN = re.compile(r'margin[^:]*:\s*[^;]*-\d', re.IGNORECASE)
    RE_CSS_MAX_DIM = re.compile(r'max-(?:width|height)\s*:', re.IGNORECASE)
    RE_CSS_PSEUDO_UNSUPPORTED = re.compile(r':(?:nth-child|first-child|visited)\b', re.IGNORECASE)
    RE_CSS_PSEUDO_ELEMENT = re.compile(r'::(?:before|after)\b', re.IGNORECASE)
    RE_CSS_LINEAR_GRADIENT = re.compile(r'linear-gradient\s*\(', re.IGNORECASE)
    RE_CSS_CAPTION_SIDE = re.compile(r'caption-side\s*:\s*bottom', re.IGNORECASE)
    RE_CSS_BODY_FONT_OVERRIDE = re.compile(r'body\s*\{[^}]*font-family\s*:', re.IGNORECASE | re.DOTALL)
    RE_NBSP_EXCESSIVE = re.compile(r'(?:&nbsp;|&#160;)\s*(?:&nbsp;|&#160;)\s*(?:&nbsp;|&#160;)', re.IGNORECASE)
    RE_CSS_COLOR_FORCE = re.compile(r'(?<![a-zA-Z-])color\s*:\s*(?:#[0-9a-fA-F]{3,6}|rgb)', re.IGNORECASE)
    RE_CSS_BODY_BOLD = re.compile(r'body\s*\{[^}]*font-weight\s*:\s*bold', re.IGNORECASE | re.DOTALL)
    RE_CSS_BODY_ITALIC = re.compile(r'body\s*\{[^}]*font-style\s*:\s*italic', re.IGNORECASE | re.DOTALL)

    # Namespaces commonly used in EPUB
    NAMESPACES = {
        'opf': 'http://www.idpf.org/2007/opf',
        'dc': 'http://purl.org/dc/elements/1.1/',
        'dcterms': 'http://purl.org/dc/terms/',
        'xhtml': 'http://www.w3.org/1999/xhtml',
        'epub': 'http://www.idpf.org/2007/ops',
        'container': 'urn:oasis:names:tc:opendocument:xmlns:container'
    }
    
    def __init__(self, epub_path: str):
        self.epub_path = Path(epub_path)
        self.issues = {
            'pc_reader': [],
            'apple_books': [],
            'pocketbook': [],
            'kindle': [],
            'kobo': [],
            'inkbook': [],
            'android': [],
            'general': []
        }
        self.warnings = {
            'pc_reader': [],
            'apple_books': [],
            'pocketbook': [],
            'kindle': [],
            'kobo': [],
            'inkbook': [],
            'android': [],
            'general': []
        }
        self.info = {
            'title': 'Unknown',
            'author': 'Unknown',
            'version': 'Unknown',
            'identifier': None,
            'file_count': 0,
            'image_count': 0,
            'css_count': 0
        }
        # Cache for file contents to avoid redundant reads
        self._content_cache: Dict[str, str] = {}
    
    def _is_safe_path(self, path: str) -> bool:
        """Check if path is safe (no directory traversal)"""
        normalized = os.path.normpath(path)
        return not normalized.startswith('..') and not os.path.isabs(normalized)
    
    def _check_zip_safety(self, epub: zipfile.ZipFile) -> bool:
        """Check for potential zip bombs"""
        total_uncompressed = sum(f.file_size for f in epub.infolist())
        total_compressed = sum(f.compress_size for f in epub.infolist())
        
        if total_uncompressed > self.MAX_UNCOMPRESSED_SIZE:
            self.issues['general'].append(
                f"EPUB uncompressed size ({total_uncompressed / 1024 / 1024:.1f}MB) exceeds safety limit"
            )
            return False
        
        if total_compressed > 0:
            ratio = total_uncompressed / total_compressed
            if ratio > self.MAX_COMPRESSION_RATIO:
                self.issues['general'].append(
                    f"Suspicious compression ratio ({ratio:.1f}:1) - possible zip bomb"
                )
                return False
        
        return True
    
    def _read_file_cached(self, epub: zipfile.ZipFile, path: str) -> Optional[str]:
        """Read file content with caching and safety checks"""
        if path in self._content_cache:
            return self._content_cache[path]
        
        if not self._is_safe_path(path):
            self.issues['general'].append(f"Unsafe path detected: '{path}'")
            return None
        
        try:
            content = epub.read(path).decode('utf-8', errors='ignore')
            self._content_cache[path] = content
            return content
        except KeyError:
            return None
        except (IOError, UnicodeDecodeError) as e:
            self.warnings['general'].append(f"Error reading '{path}': {str(e)}")
            return None
        
    def validate(self) -> Optional[Dict]:
        """Run all validation checks"""
        if not self.epub_path.exists():
            print(f"Error: File '{self.epub_path}' does not exist")
            return None
            
        if not zipfile.is_zipfile(self.epub_path):
            print(f"Error: '{self.epub_path}' is not a valid ZIP/EPUB file")
            return None
        
        try:
            with zipfile.ZipFile(self.epub_path, 'r') as epub:
                # Security check first
                if not self._check_zip_safety(epub):
                    return self._generate_report()
                
                # Basic structure checks
                self._check_mimetype(epub)
                self._check_container(epub)
                
                # Get OPF file
                opf_path = self._get_opf_path(epub)
                if not opf_path:
                    self.issues['general'].append("Could not find OPF file")
                    return self._generate_report()
                
                # Parse OPF
                opf_content = epub.read(opf_path).decode('utf-8')
                opf_root = ET.fromstring(opf_content)
                
                # Extract metadata
                self._extract_metadata(opf_root)
                
                # Get manifest and spine
                manifest = self._parse_manifest(opf_root, opf_path)
                spine = self._parse_spine(opf_root)
                
                # File statistics
                self.info['file_count'] = len(epub.namelist())
                
                # Content validation
                self._validate_content_files(epub, manifest)
                self._validate_images(epub, manifest)
                self._validate_css(epub, manifest)
                self._validate_fonts(epub, manifest)
                self._check_drm(epub)
                self._check_file_sizes(epub)
                
                # Additional structural validation
                self._validate_navigation(epub, opf_root, manifest)
                self._validate_spine_references(manifest, spine)
                self._validate_ids(epub, manifest)
                self._validate_links(epub, manifest)
                
                # Platform-specific checks
                self._check_pc_reader_issues(opf_root, manifest)
                self._check_apple_books_issues(opf_root, manifest)
                self._check_pocketbook_issues(opf_root, manifest)
                self._check_kindle_issues(opf_root, manifest, spine, epub)
                self._check_kobo_issues(opf_root, manifest)
                self._check_inkbook_issues(opf_root, manifest)
                self._check_android_issues(opf_root, manifest)
                
        except (zipfile.BadZipFile, ET.ParseError, IOError, OSError) as e:
            self.issues['general'].append(f"Error processing EPUB: {str(e)}")
        except Exception as e:
            # Catch remaining exceptions but don't hide SystemExit/KeyboardInterrupt
            if isinstance(e, (SystemExit, KeyboardInterrupt)):
                raise
            self.issues['general'].append(f"Unexpected error processing EPUB: {str(e)}")
        
        return self._generate_report()
    
    def _check_mimetype(self, epub: zipfile.ZipFile):
        """Check mimetype file exists, is correct, and is uncompressed"""
        try:
            # Check content
            mimetype = epub.read('mimetype').decode('utf-8').strip()
            if mimetype != 'application/epub+zip':
                self.issues['general'].append(
                    f"Invalid mimetype: '{mimetype}' (should be 'application/epub+zip')"
                )
            
            # Check compression (EPUB OCF spec requires uncompressed)
            info = epub.getinfo('mimetype')
            if info.compress_type != zipfile.ZIP_STORED:
                self.warnings['general'].append(
                    "Mimetype file is compressed (EPUB OCF 3.0 § 3.3 requires uncompressed)"
                )
            
            # Check if it's the first file (optional but recommended)
            if epub.namelist()[0] != 'mimetype':
                self.warnings['general'].append(
                    "Mimetype is not first file in ZIP (EPUB OCF 3.0 § 3.3 recommends first)"
                )
        except KeyError:
            self.issues['general'].append("Missing 'mimetype' file")
    
    def _check_container(self, epub: zipfile.ZipFile):
        """Check META-INF/container.xml exists"""
        try:
            epub.read('META-INF/container.xml')
        except KeyError:
            self.issues['general'].append("Missing 'META-INF/container.xml' file")
    
    def _get_opf_path(self, epub: zipfile.ZipFile) -> Optional[str]:
        """Get the path to the OPF file from container.xml"""
        try:
            container_xml = epub.read('META-INF/container.xml').decode('utf-8')
            container_root = ET.fromstring(container_xml)
            
            rootfile = container_root.find('.//container:rootfile', self.NAMESPACES)
            if rootfile is not None:
                return rootfile.get('full-path')
        except (KeyError, ET.ParseError, UnicodeDecodeError) as e:
            self.issues['general'].append(f"Error parsing container.xml: {str(e)}")
        
        return None
    
    def _extract_metadata(self, opf_root: ET.Element):
        """Extract basic metadata from OPF"""
        metadata = opf_root.find('.//opf:metadata', self.NAMESPACES)
        if metadata is not None:
            # Title
            title = metadata.find('.//dc:title', self.NAMESPACES)
            if title is not None and title.text:
                self.info['title'] = title.text
            
            # Author
            creator = metadata.find('.//dc:creator', self.NAMESPACES)
            if creator is not None and creator.text:
                self.info['author'] = creator.text
            
            # Language (REQUIRED by EPUB spec)
            language = metadata.find('.//dc:language', self.NAMESPACES)
            if language is None or not language.text:
                self.issues['general'].append(
                    "Missing dc:language metadata (REQUIRED by EPUB specification - EPUB 3.3 § 4.2.2)"
                )
            else:
                lang_code = language.text.strip()
                # Validate BCP 47 format using pre-compiled pattern
                if not self.RE_BCP47.match(lang_code):
                    self.warnings['general'].append(
                        f"Invalid language code '{lang_code}' - should be BCP 47 format (e.g., 'en', 'en-US', 'zh-Hans')"
                    )
                self.info['language'] = lang_code

            # Identifier
            identifier = metadata.find('.//dc:identifier', self.NAMESPACES)
            if identifier is not None and identifier.text:
                self.info['identifier'] = identifier.text.strip()

        # EPUB version
        package = opf_root
        version = package.get('version', 'Unknown')
        self.info['version'] = version
    
    def _parse_manifest(self, opf_root: ET.Element, opf_path: str) -> Dict:
        """Parse manifest to get all file references"""
        manifest = {}
        manifest_elem = opf_root.find('.//opf:manifest', self.NAMESPACES)
        
        if manifest_elem is not None:
            opf_dir = str(Path(opf_path).parent)
            for item in manifest_elem.findall('.//opf:item', self.NAMESPACES):
                item_id = item.get('id')
                href = item.get('href')
                media_type = item.get('media-type')
                properties = item.get('properties', '')
                
                if href:
                    # Resolve path relative to OPF
                    if opf_dir and opf_dir != '.':
                        full_path = str(Path(opf_dir) / href)
                    else:
                        full_path = href
                    
                    manifest[item_id] = {
                        'href': full_path,
                        'media_type': media_type,
                        'properties': properties
                    }
        
        return manifest
    
    def _parse_spine(self, opf_root: ET.Element) -> List[Dict]:
        """Parse spine to get reading order"""
        spine = []
        spine_elem = opf_root.find('.//opf:spine', self.NAMESPACES)
        
        if spine_elem is not None:
            for itemref in spine_elem.findall('.//opf:itemref', self.NAMESPACES):
                idref = itemref.get('idref')
                linear = itemref.get('linear', 'yes')  # Default per spec
                
                if linear not in ['yes', 'no']:
                    self.issues['general'].append(
                        f"Invalid linear attribute '{linear}' in spine itemref '{idref}' (must be 'yes' or 'no')"
                    )
                
                if idref:
                    spine.append({'idref': idref, 'linear': linear})
        
        return spine
    
    def _validate_content_files(self, epub: zipfile.ZipFile, manifest: Dict):
        """Validate XHTML/HTML content files"""
        xhtml_count = 0
        
        for item_id, item_info in manifest.items():
            media_type = item_info['media_type']
            href = item_info['href']
            
            if media_type in ['application/xhtml+xml', 'text/html']:
                xhtml_count += 1
                
                content = self._read_file_cached(epub, href)
                if content is None:
                    self.issues['general'].append(f"Referenced file not found: '{href}'")
                    continue
                
                # Check for HTML entities without proper declaration
                self._check_html_entities(content, href)
                
                # Check for XML/XHTML validity issues
                self._check_xhtml_validity(content, href)
                
                # Check for common issues using pre-compiled patterns
                content_no_comments = self.RE_COMMENT.sub('', content)
                if self.RE_SCRIPT_TAG.search(content_no_comments):
                    self.warnings['general'].append(
                        f"JavaScript found in '{href}' (limited support on e-readers)"
                    )
                
                # Check for embedded styles (warning for Kindle)
                # Only warn if extensive inline styles (avoid noise on minimal usage)
                inline_style_count = content.count('style=')
                if inline_style_count > 10:  # Threshold for concern
                    self.warnings['kindle'].append(
                        f"Extensive inline styles ({inline_style_count} instances) in '{href}' "
                        f"may not render correctly on older Kindles - consider moving to CSS"
                    )
                
                # Check for layout issues
                self._check_layout_issues(content, href)
        
        if xhtml_count == 0:
            self.issues['general'].append("No content files found in manifest")
    
    def _check_html_entities(self, content: str, file_path: str):
        """Check for HTML entities that need proper declaration for Apple Books"""
        # Common HTML entities that cause issues in XHTML
        problematic_entities = [
            ('&nbsp;', '&#160;', 'nbsp'),
            ('&ndash;', '&#8211;', 'ndash'),
            ('&mdash;', '&#8212;', 'mdash'),
            ('&hellip;', '&#8230;', 'hellip'),
            ('&rsquo;', '&#8217;', 'rsquo'),
            ('&lsquo;', '&#8216;', 'lsquo'),
            ('&rdquo;', '&#8221;', 'rdquo'),
            ('&ldquo;', '&#8220;', 'ldquo'),
            ('&copy;', '&#169;', 'copy'),
            ('&reg;', '&#174;', 'reg'),
            ('&trade;', '&#8482;', 'trade'),
        ]
        
        # Track entities we've already reported for this file to avoid duplicates
        reported_entities = set()
        
        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            for entity, numeric_entity, entity_name in problematic_entities:
                if entity in line and entity_name not in reported_entities:
                    # Check if DOCTYPE declares HTML entities (more precise)
                    has_entity_dtd = False
                    if '<!DOCTYPE' in content:
                        # Check for XHTML 1.x DTD that includes entity declarations
                        if any(dtd in content for dtd in [
                            'xhtml1-strict.dtd',
                            'xhtml1-transitional.dtd', 
                            'xhtml11.dtd',
                            'xhtml-lat1.ent',
                            'xhtml-special.ent',
                            'xhtml-symbol.ent'
                        ]):
                            has_entity_dtd = True
                    
                    if not has_entity_dtd:
                        reported_entities.add(entity_name)
                        self.issues['apple_books'].append(
                            f"{file_path} (line {line_num}): Undeclared entity '{entity_name}' - "
                            f"Replace {entity} with {numeric_entity} or add proper DOCTYPE"
                        )
                        # Note: Don't duplicate in general issues - it's already covered in Apple Books
    
    def _check_xhtml_validity(self, content: str, file_path: str):
        """Check if XHTML is valid XML"""
        try:
            # Attempt to parse the XML
            # We wrap content in a dummy root to handle potential multiple root issues in fragments
            # though valid XHTML should have one html root.
            ET.fromstring(content.encode('utf-8'))
        except ET.ParseError as e:
            # This is crucial: Report the specific XML error
            # Extract the specific line for context
            lines = content.splitlines()
            context = ""
            line_num = "Unknown"
            try:
                line_num, col = e.position
                if 0 <= line_num - 1 < len(lines):
                    context = lines[line_num - 1].strip()
            except (AttributeError, TypeError):
                # Some older python versions might not have position attribute easily accessible or different error structure
                context = "Unknown context"

            # Check if this is an entity error (already reported by _check_html_entities)
            # Don't duplicate the error message
            if "undefined entity" in str(e).lower():
                # Entity errors are already detailed in _check_html_entities
                # Only add a note about XML validity impact
                pass  # Skip - already reported with better context
            else:
                # Report other XML parsing errors
                msg = f"XML Parsing Error: {str(e)}"
                self.issues['general'].append(
                    f"{file_path} (line {line_num}): {msg}"
                )
    
    def _check_layout_issues(self, content: str, file_path: str):
        """Check for potential layout issues on PocketBook and other readers"""
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            # Check for absolute positioning
            if 'position:absolute' in line or 'position: absolute' in line:
                self.warnings['pocketbook'].append(
                    f"{file_path} (line {line_num}): Absolute positioning may cause layout issues"
                )
            
            # Check for fixed positioning
            if 'position:fixed' in line or 'position: fixed' in line:
                self.warnings['pocketbook'].append(
                    f"{file_path} (line {line_num}): Fixed positioning not supported"
                )
            
            # Check for large margin values in inline styles (CRITICAL for PocketBook)
            # Large margins (especially in em units) cause text layout to become mixed/unreadable
            large_margin_match = self.RE_LARGE_MARGIN.search(line)
            if large_margin_match:
                value = float(large_margin_match.group(1))
                unit = large_margin_match.group(2)
                if value >= 5:  # 5em or more is problematic
                    self.issues['pocketbook'].append(
                        f"{file_path} (line {line_num}): Large margin value ({value}{unit}) breaks text layout on PocketBook - "
                        f"causes mixed/unreadable pages. Use smaller values (max 2em) or move to CSS file"
                    )
                    self.issues['inkbook'].append(
                        f"{file_path} (line {line_num}): Large margin value ({value}{unit}) may break layout on InkBook"
                    )
            
            # Check for viewport units
            if self.RE_VIEWPORT_UNITS.search(line):
                self.warnings['pocketbook'].append(
                    f"{file_path} (line {line_num}): Viewport units may not work correctly"
                )
            
            # Check for transforms (using pre-compiled pattern)
            if self.RE_TRANSFORM.search(line):
                self.warnings['pocketbook'].append(
                    f"{file_path} (line {line_num}): CSS transforms may not be supported"
                )
    
    def _validate_images(self, epub: zipfile.ZipFile, manifest: Dict):
        """Validate images and check formats"""
        image_types = ['image/jpeg', 'image/png', 'image/gif', 'image/svg+xml']
        image_count = 0
        missing_images = set()
        
        for item_id, item_info in manifest.items():
            media_type = item_info['media_type']
            href = item_info['href']
            
            if media_type in image_types:
                image_count += 1
                
                try:
                    img_data = epub.read(href)
                    img_size = len(img_data)
                    
                    # Check image size (> 5MB warning)
                    if img_size > 5 * 1024 * 1024:
                        self.warnings['general'].append(
                            f"Large image '{href}' ({img_size / 1024 / 1024:.1f}MB) - consider optimizing"
                        )
                    elif img_size > 2 * 1024 * 1024:
                        self.warnings['general'].append(
                            f"Image '{href}' ({img_size / 1024 / 1024:.1f}MB) - consider optimizing for better performance"
                        )
                    
                    # Check image dimensions if possible
                    if media_type in ['image/jpeg', 'image/png']:
                        width, height = self._get_image_dimensions(img_data, media_type)
                        if width and height:
                            # Adjust threshold for legitimate high-DPI covers
                            if width > 3000 or height > 4000:
                                self.warnings['general'].append(
                                    f"Very large image dimensions '{href}' ({width}x{height}px) - "
                                    f"consider if this resolution is necessary for e-readers"
                                )
                            elif width > 2000 or height > 2000:
                                # Only info for moderately large images
                                if 'high_res_images' not in self.info:
                                    self.info['high_res_images'] = 0
                                self.info['high_res_images'] += 1
                    
                    # SVG warnings
                    if media_type == 'image/svg+xml':
                        self.warnings['pocketbook'].append(
                            f"SVG image '{href}' may have limited support on PocketBook"
                        )
                        self.warnings['kindle'].append(
                            f"SVG image '{href}' not supported on older Kindle devices"
                        )
                    
                    # GIF warnings
                    if media_type == 'image/gif':
                        self.warnings['kindle'].append(
                            f"GIF image '{href}' - Kindle converts to grayscale"
                        )
                
                except KeyError:
                    missing_images.add(href)
                    self.issues['general'].append(f"Missing image: '{href}' (declared in manifest but file not found)")
        
        self.info['image_count'] = image_count
        
        # Check for cover image designation
        cover_items = [item for item in manifest.values() if 'cover-image' in item.get('properties', '')]
        
        if len(cover_items) == 0:
            self.warnings['general'].append(
                "No cover image designated with properties='cover-image' in manifest (EPUB 3.3 \u00a7 3.2)"
            )
        elif len(cover_items) > 1:
            self.issues['general'].append(
                f"Multiple cover images declared ({len(cover_items)} items) - only one allowed"
            )
        else:
            # Validate cover dimensions
            cover = cover_items[0]
            try:
                img_data = epub.read(cover['href'])
                width, height = self._get_image_dimensions(img_data, cover['media_type'])
                if width and height:
                    if width < 300 or height < 400:
                        self.warnings['general'].append(
                            f"Cover image dimensions ({width}x{height}px) too small - "
                            f"recommend minimum 1000x1400px for quality"
                        )
            except (KeyError, IOError, struct.error):
                pass  # Cover file missing or unreadable
        
        # Track which files reference missing images
        if missing_images:
            self._find_image_references(epub, manifest, missing_images)
    
    def _get_image_dimensions(self, img_data: bytes, media_type: str) -> Tuple[Optional[int], Optional[int]]:
        """Extract image dimensions from JPEG or PNG data"""
        try:
            if media_type == 'image/png' and len(img_data) > 24:
                # PNG dimensions are at bytes 16-24
                width, height = struct.unpack('>II', img_data[16:24])
                return width, height
            elif media_type == 'image/jpeg':
                # Basic JPEG dimension extraction
                i = 0
                while i < len(img_data) - 9:
                    if img_data[i] == 0xFF:
                        if img_data[i+1] in [0xC0, 0xC1, 0xC2]:
                            height, width = struct.unpack('>HH', img_data[i+5:i+9])
                            return width, height
                    i += 1
        except struct.error:
            pass
        return None, None
    
    def _find_image_references(self, epub: zipfile.ZipFile, manifest: Dict, missing_images: Set[str]):
        """Find which XHTML files reference missing images"""
        for item_id, item_info in manifest.items():
            if item_info['media_type'] in ['application/xhtml+xml', 'text/html']:
                content = self._read_file_cached(epub, item_info['href'])
                if content:
                    for missing_img in missing_images:
                        img_name = missing_img.split('/')[-1]
                        if img_name in content or missing_img in content:
                            self.issues['general'].append(
                                f"File '{item_info['href']}' references missing image '{missing_img}'"
                            )
    
    def _validate_css(self, epub: zipfile.ZipFile, manifest: Dict):
        """Validate CSS files for platform compatibility"""
        css_files = [item for item in manifest.values() if item['media_type'] == 'text/css']
        
        for css_file in css_files:
            href = css_file['href']
            try:
                with epub.open(href) as f:
                    content = f.read().decode('utf-8', errors='ignore')
                    
                # Remove comments using pre-compiled pattern
                clean_content = self.RE_CSS_COMMENT.sub('', content)
                
                lines = content.splitlines() # Keep original for line numbers
                
                # Check for PocketBook/InkBook issues (CSS Transforms)
                # Note: text-transform is NOT the same as transform!
                # text-transform: uppercase/lowercase/capitalize - SAFE
                # transform: rotate/scale/translate - BREAKS RENDERING
                
                # Look for transform property using pre-compiled pattern
                if self.RE_TRANSFORM.search(clean_content):
                    for i, line in enumerate(lines, 1):
                        # Check if line is not commented out (simple check)
                        if self.RE_TRANSFORM.search(line) and not line.strip().startswith('/*'):
                            msg = f"CSS transform detected (stops rendering on PocketBook/InkBook): {line.strip()[:50]}..."
                            self.issues['pocketbook'].append(f"{href} (line {i}): {msg}")
                            self.issues['inkbook'].append(f"{href} (line {i}): {msg}")

                # Check for absolute positioning (often bad for reflowable)
                if 'position: absolute' in clean_content or 'position:absolute' in clean_content:
                    self.warnings['general'].append(
                        f"{href}: Absolute positioning detected (may break reflowable layout)"
                    )
                    
            except (KeyError, IOError, UnicodeDecodeError) as e:
                self.issues['general'].append(f"Could not parse CSS file '{href}': {str(e)}")        
        self.info['css_count'] = len(css_files)
    
    def _validate_navigation(self, epub: zipfile.ZipFile, opf_root: ET.Element, manifest: Dict):
        """Validate NCX (EPUB 2) or nav.xhtml (EPUB 3) navigation documents"""
        version = self.info['version']
        
        if version.startswith('2'):
            # Check for toc.ncx in EPUB 2
            ncx_items = [item for item in manifest.values() if item['media_type'] == 'application/x-dtbncx+xml']
            if not ncx_items:
                self.issues['general'].append(
                    "Missing toc.ncx file (required in EPUB 2.0 - EPUB 2.0.1 \u00a7 2.4.1)"
                )
        
        elif version.startswith('3'):
            # Check for nav document in EPUB 3
            nav_items = [item for item in manifest.values() if 'nav' in item.get('properties', '')]
            if not nav_items:
                self.issues['general'].append(
                    "Missing navigation document with properties='nav' (required in EPUB 3 - EPUB 3.3 \u00a7 5.4)"
                )
            elif len(nav_items) > 1:
                self.issues['general'].append(
                    f"Multiple navigation documents declared ({len(nav_items)}) - only one allowed"
                )
    
    def _validate_spine_references(self, manifest: Dict, spine: List):
        """Validate that spine itemrefs reference valid manifest items"""
        for spine_item in spine:
            idref = spine_item.get('idref') if isinstance(spine_item, dict) else spine_item
            if idref and idref not in manifest:
                self.issues['general'].append(
                    f"Spine references non-existent manifest item: '{idref}' (EPUB 3.3 \u00a7 4.3)"
                )
    
    def _validate_ids(self, epub: zipfile.ZipFile, manifest: Dict):
        """Validate ID uniqueness across all content documents"""
        all_ids = defaultdict(list)  # id -> [files using it]
        
        for item_id, item_info in manifest.items():
            if item_info['media_type'] in ['application/xhtml+xml', 'text/html']:
                content = self._read_file_cached(epub, item_info['href'])
                if content:
                    # Find all id attributes using pre-compiled regex
                    for match in self.RE_ID_ATTR.finditer(content):
                        elem_id = match.group(1)
                        all_ids[elem_id].append(item_info['href'])
        
        # Check for duplicates across files
        for elem_id, files in all_ids.items():
            if len(files) > 1:
                self.issues['general'].append(
                    f"Duplicate ID '{elem_id}' found in multiple files: {', '.join(files[:3])}{'...' if len(files) > 3 else ''} (XML 1.0 \u00a7 3.3.1)"
                )
    
    def _validate_links(self, epub: zipfile.ZipFile, manifest: Dict):
        """Validate all internal links and references"""
        # Build set of valid files
        valid_files = {item['href'] for item in manifest.values()}
        
        # Collect all IDs per file using cached content
        file_ids = defaultdict(set)  # file -> set of IDs
        for item_id, item_info in manifest.items():
            if item_info['media_type'] in ['application/xhtml+xml', 'text/html']:
                content = self._read_file_cached(epub, item_info['href'])
                if content:
                    for match in self.RE_ID_ATTR.finditer(content):
                        elem_id = match.group(1)
                        file_ids[item_info['href']].add(elem_id)
        
        # Validate links
        for item_id, item_info in manifest.items():
            if item_info['media_type'] in ['application/xhtml+xml', 'text/html']:
                content = self._read_file_cached(epub, item_info['href'])
                if not content:
                    continue
                
                # Find all href attributes using pre-compiled regex
                for match in self.RE_HREF_ATTR.finditer(content):
                    href = match.group(1)
                    
                    # Skip external links and pure fragments
                    if href.startswith(('http://', 'https://', 'mailto:', 'ftp://', 'data:')):
                        continue
                    if href.startswith('#'):
                        # Local fragment - validate against current file IDs
                        fragment = href[1:]
                        if fragment and fragment not in file_ids.get(item_info['href'], set()):
                            self.issues['general'].append(
                                f"{item_info['href']}: Broken link to '#{fragment}' (ID not found in same file)"
                            )
                        continue
                    
                    # Parse file and fragment
                    if '#' in href:
                        file_part, fragment = href.split('#', 1)
                    else:
                        file_part, fragment = href, None
                    
                    # Resolve relative path
                    if file_part:
                        base_dir = str(Path(item_info['href']).parent)
                        if base_dir == '.':
                            target_file = file_part
                        else:
                            target_file = str((Path(base_dir) / file_part).as_posix())
                        
                        # Normalize path
                        target_file = target_file.replace('//', '/')
                        
                        if target_file not in valid_files:
                            self.issues['general'].append(
                                f"{item_info['href']}: Broken link to '{href}' (file not found in manifest)"
                            )
                        elif fragment and fragment not in file_ids.get(target_file, set()):
                            self.warnings['general'].append(
                                f"{item_info['href']}: Link to '{href}' - fragment ID '{fragment}' not found in target"
                            )
    
    def _validate_fonts(self, epub: zipfile.ZipFile, manifest: Dict):
        """Validate embedded fonts"""
        font_types = [
            'application/vnd.ms-opentype',
            'application/x-font-ttf',
            'application/x-font-truetype',
            'application/x-font-otf',
            'font/ttf',
            'font/otf',
            'font/woff',
            'font/woff2'
        ]
        
        font_count = 0
        
        for item_id, item_info in manifest.items():
            media_type = item_info['media_type']
            href = item_info['href']
            
            if media_type in font_types or href.lower().endswith(('.ttf', '.otf', '.woff', '.woff2')):
                font_count += 1
                
                # WOFF/WOFF2 warnings
                if '.woff' in href.lower():
                    self.warnings['pocketbook'].append(
                        f"WOFF font '{href}' may not be supported on all PocketBook models"
                    )
        
        if font_count > 0:
            self.info['font_count'] = font_count
    
    def _check_drm(self, epub: zipfile.ZipFile):
        """Check for DRM indicators"""
        try:
            # Check for encryption.xml
            encryption = epub.read('META-INF/encryption.xml').decode('utf-8')
            if 'encryption' in encryption.lower():
                self.issues['general'].append(
                    "DRM/Encryption detected - may not be readable on all devices"
                )
        except KeyError:
            pass  # No encryption file is normal
    
    def _check_file_sizes(self, epub: zipfile.ZipFile):
        """Check overall file size"""
        file_size = self.epub_path.stat().st_size
        file_size_mb = file_size / 1024 / 1024
        
        self.info['file_size_mb'] = f"{file_size_mb:.2f}"
        
        if file_size_mb > 100:
            self.warnings['general'].append(
                f"Large file size ({file_size_mb:.1f}MB) may cause performance issues"
            )
        
        if file_size_mb > 650:
            self.issues['kindle'].append(
                f"File too large for Kindle email delivery ({file_size_mb:.1f}MB > 650MB limit)"
            )
    
    def _check_pc_reader_issues(self, opf_root: ET.Element, manifest: Dict):
        """Check for PC reader (Calibre, Adobe Digital Editions, etc.) specific issues"""
        # PC readers are generally most compatible, so fewer issues
        
        # Check for fixed layout
        metadata = opf_root.find('.//opf:metadata', self.NAMESPACES)
        if metadata is not None:
            for meta in metadata.findall('.//opf:meta', self.NAMESPACES):
                property_attr = meta.get('property', '')
                if property_attr == 'rendition:layout' and meta.text == 'pre-paginated':
                    self.warnings['pc_reader'].append(
                        "Fixed layout EPUB - may not reflow text properly"
                    )
    
    def _check_apple_books_issues(self, opf_root: ET.Element, manifest: Dict):
        """Check for Apple Books specific issues"""
        # Check for iBooks-specific features
        metadata = opf_root.find('.//opf:metadata', self.NAMESPACES)
        if metadata is not None:
            # Check for interactive widgets
            for meta in metadata.findall('.//opf:meta', self.NAMESPACES):
                property_attr = meta.get('property', '')
                if 'ibooks:' in property_attr:
                    self.warnings['apple_books'].append(
                        f"iBooks-specific feature detected: {property_attr} (not portable to other readers)"
                    )
        
        # Check for Apple-specific media
        for item_id, item_info in manifest.items():
            media_type = item_info['media_type']
            properties = item_info['properties']
            
            if 'scripted' in properties:
                self.warnings['apple_books'].append(
                    f"Scripted content in '{item_info['href']}' - Apple Books specific"
                )
    
    def _check_pocketbook_issues(self, opf_root: ET.Element, manifest: Dict):
        """Check for PocketBook specific issues"""
        # PocketBook has good EPUB support but some limitations
        
        # Check for complex CSS
        for item_id, item_info in manifest.items():
            if item_info['media_type'] == 'text/css':
                # Already handled in CSS validation
                pass
        
        # Check for MathML
        for item_id, item_info in manifest.items():
            media_type = item_info['media_type']
            if media_type in ['application/xhtml+xml', 'text/html']:
                # Would need to parse content for MathML - simplified check
                properties = item_info['properties']
                if 'mathml' in properties.lower():
                    self.warnings['pocketbook'].append(
                        f"MathML content may have limited support on PocketBook"
                    )
    
    def _check_kobo_issues(self, opf_root: ET.Element, manifest: Dict):
        """Check for Kobo specific issues"""
        # Kobo has good EPUB support, similar to PC readers but with some quirks
        
        # Check for Kobo-specific enhancements (optional)
        metadata = opf_root.find('.//opf:metadata', self.NAMESPACES)
        if metadata is not None:
            for meta in metadata.findall('.//opf:meta', self.NAMESPACES):
                property_attr = meta.get('property', '')
                if 'kobo:' in property_attr:
                    self.warnings['kobo'].append(
                        f"Kobo-specific feature detected: {property_attr} (not portable to other readers)"
                    )
        
        # Check for large images (Kobo can be slower with large images)
        for item_id, item_info in manifest.items():
            media_type = item_info['media_type']
            if media_type in ['image/jpeg', 'image/png']:
                # Already checked in general validation
                pass
        
        # Kobo handles most CSS well, but check for some edge cases
        for item_id, item_info in manifest.items():
            if item_info['media_type'] == 'text/css':
                href = item_info['href']
                # Most CSS works fine on Kobo, only warn about very advanced features
                # (Already covered in general CSS validation)
                pass
    
    def _check_inkbook_issues(self, opf_root: ET.Element, manifest: Dict):
        """Check for InkBook specific issues"""
        # InkBook (Polish e-reader) has similar limitations to PocketBook
        
        # InkBook has issues with CSS transforms similar to PocketBook
        for item_id, item_info in manifest.items():
            if item_info['media_type'] == 'text/css':
                href = item_info['href']
                # CSS transform issues are already detected in PocketBook checks
                # and CSS validation, so we reference those
                pass
        
        # Check for SVG support (limited)
        for item_id, item_info in manifest.items():
            media_type = item_info['media_type']
            href = item_info['href']
            
            if media_type == 'image/svg+xml':
                self.warnings['inkbook'].append(
                    f"SVG image '{href}' may have limited support on InkBook"
                )
        
        # Check for complex fonts
        metadata = opf_root.find('.//opf:metadata', self.NAMESPACES)
        if metadata is not None:
            for meta in metadata.findall('.//opf:meta', self.NAMESPACES):
                property_attr = meta.get('property', '')
                if 'rendition:layout' in property_attr:
                    self.warnings['inkbook'].append(
                        "Fixed layout may not work correctly on InkBook"
                    )
    
    def _check_android_issues(self, opf_root: ET.Element, manifest: Dict):
        """Check for Android default EPUB reader issues"""
        # Android readers vary (Google Play Books, ReadEra, Moon+ Reader, etc.)
        # Most modern Android readers have good EPUB 3 support
        
        # Check for audio/video (Google Play Books supports, others may not)
        media_types = ['audio/mpeg', 'audio/mp4', 'video/mp4', 'video/h264']
        for item_id, item_info in manifest.items():
            if item_info['media_type'] in media_types:
                self.warnings['android'].append(
                    f"Audio/Video content '{item_info['href']}' - support varies by Android reader app"
                )
        
        # Check for MathML (limited support)
        for item_id, item_info in manifest.items():
            properties = item_info.get('properties', '')
            if 'mathml' in properties.lower():
                self.warnings['android'].append(
                    "MathML content may not display correctly in all Android EPUB readers"
                )
        
        # JavaScript warnings (very limited support)
        # Already covered in general checks
    
    def _check_kindle_issues(self, opf_root: ET.Element, manifest: Dict, spine: List,
                             epub: zipfile.ZipFile = None):
        """Check for Amazon KDP specific issues (comprehensive pre-publish validation)"""
        if epub is None:
            return

        self._kdp_check_cover_image(epub, manifest, opf_root)
        self._kdp_check_metadata(opf_root)
        self._kdp_check_file_limits(epub, manifest)
        self._kdp_check_toc_quality(epub, opf_root, manifest)
        self._kdp_check_unsupported_html(epub, manifest)
        self._kdp_check_css_restrictions(epub, manifest)
        self._kdp_check_enhanced_typesetting(epub, manifest)
        self._kdp_check_image_requirements(epub, manifest)
        self._kdp_check_font_rules(manifest)
        self._kdp_check_content_quality(epub, manifest)

    def _is_cmyk_jpeg(self, img_data: bytes) -> bool:
        """Check if JPEG uses CMYK color space by examining SOF marker"""
        i = 0
        while i < len(img_data) - 9:
            if img_data[i] == 0xFF and img_data[i + 1] in (0xC0, 0xC1, 0xC2):
                num_components = img_data[i + 9]
                return num_components == 4
            i += 1
        return False

    def _kdp_check_cover_image(self, epub: zipfile.ZipFile, manifest: Dict, opf_root: ET.Element):
        """Check cover image requirements for Amazon KDP"""
        cover_items = [item for item in manifest.values()
                       if 'cover-image' in item.get('properties', '')]

        # Also check EPUB2 meta name="cover"
        if not cover_items:
            metadata = opf_root.find('.//opf:metadata', self.NAMESPACES)
            if metadata is not None:
                for meta in metadata.findall('.//opf:meta', self.NAMESPACES):
                    if meta.get('name') == 'cover':
                        cover_id = meta.get('content')
                        if cover_id and cover_id in manifest:
                            cover_items = [manifest[cover_id]]
                            break

        if not cover_items:
            self.issues['kindle'].append(
                "No cover image found - Amazon KDP REQUIRES a cover image for publishing"
            )
            return

        cover = cover_items[0]

        # Check format (JPEG or PNG only)
        if cover['media_type'] not in ('image/jpeg', 'image/png'):
            self.issues['kindle'].append(
                f"Cover image format '{cover['media_type']}' not accepted - KDP requires JPEG or PNG"
            )

        try:
            img_data = epub.read(cover['href'])
            width, height = self._get_image_dimensions(img_data, cover['media_type'])
            if width and height:
                # Minimum dimensions
                if width < 625 or height < 1000:
                    self.issues['kindle'].append(
                        f"Cover too small ({width}x{height}px) - KDP minimum is 625x1000px"
                    )
                elif width < 1600 or height < 2560:
                    self.warnings['kindle'].append(
                        f"Cover image ({width}x{height}px) below ideal - KDP recommends 1600x2560px"
                    )

                # Maximum dimensions
                if width > 10000 or height > 10000:
                    self.issues['kindle'].append(
                        f"Cover too large ({width}x{height}px) - KDP maximum dimension is 10000px"
                    )

            # CMYK detection for JPEG
            if cover['media_type'] == 'image/jpeg' and self._is_cmyk_jpeg(img_data):
                self.warnings['kindle'].append(
                    "Cover image uses CMYK color space - KDP converts to sRGB which may shift colors"
                )
        except (KeyError, IOError, struct.error):
            pass

    def _kdp_check_metadata(self, opf_root: ET.Element):
        """Check metadata requirements for Amazon KDP"""
        metadata = opf_root.find('.//opf:metadata', self.NAMESPACES)
        if metadata is None:
            self.issues['kindle'].append(
                "No metadata section found - KDP requires title, author, and identifier"
            )
            return

        # dc:identifier is REQUIRED for KDP
        identifier = metadata.find('.//dc:identifier', self.NAMESPACES)
        if identifier is None or not (identifier.text and identifier.text.strip()):
            self.issues['kindle'].append(
                "Missing dc:identifier - Amazon KDP REQUIRES a unique book identifier (ISBN, ASIN, or UUID)"
            )

        # dc:title
        title = metadata.find('.//dc:title', self.NAMESPACES)
        if title is None or not (title.text and title.text.strip()):
            self.issues['kindle'].append(
                "Missing dc:title - Amazon KDP requires a book title in metadata"
            )

        # dc:creator
        creator = metadata.find('.//dc:creator', self.NAMESPACES)
        if creator is None or not (creator.text and creator.text.strip()):
            self.warnings['kindle'].append(
                "Missing dc:creator - Amazon KDP recommends author name in metadata"
            )

    def _kdp_check_file_limits(self, epub: zipfile.ZipFile, manifest: Dict):
        """Check KDP file count and size limits"""
        html_count = 0
        for item_id, item_info in manifest.items():
            if item_info['media_type'] in ('application/xhtml+xml', 'text/html'):
                html_count += 1
                try:
                    info = epub.getinfo(item_info['href'])
                    size_mb = info.file_size / (1024 * 1024)
                    if size_mb > 30:
                        self.issues['kindle'].append(
                            f"HTML file '{item_info['href']}' ({size_mb:.1f}MB) exceeds KDP 30MB per-file limit"
                        )
                except KeyError:
                    pass

        if html_count > 300:
            self.issues['kindle'].append(
                f"Too many HTML files ({html_count}) - KDP may reject EPUBs with more than 300 content files"
            )

    def _kdp_check_toc_quality(self, epub: zipfile.ZipFile, opf_root: ET.Element, manifest: Dict):
        """Check table of contents quality for Amazon KDP"""
        version = self.info.get('version', '')
        nav_content = None
        nav_href = None

        # Find nav document (EPUB3) or NCX (EPUB2)
        if version.startswith('3'):
            for item_id, item_info in manifest.items():
                if 'nav' in item_info.get('properties', ''):
                    nav_href = item_info['href']
                    nav_content = self._read_file_cached(epub, nav_href)
                    break

        if nav_content is None:
            for item_id, item_info in manifest.items():
                if item_info['media_type'] == 'application/x-dtbncx+xml':
                    nav_href = item_info['href']
                    nav_content = self._read_file_cached(epub, nav_href)
                    break

        if nav_content is None:
            self.issues['kindle'].append(
                "No table of contents found - Amazon KDP REQUIRES a functional TOC"
            )
            return

        # Check for table-based TOC layout
        if '<table' in nav_content.lower():
            self.warnings['kindle'].append(
                f"TOC uses <table> layout ({nav_href}) - KDP recommends list-based navigation"
            )

        # Check for page numbers in TOC (common in print conversions)
        page_pattern = re.compile(
            r'>\s*.*?\.\s*\.\s*\.\s*\d+\s*<|>\s*page\s+\d+\s*<', re.IGNORECASE
        )
        if page_pattern.search(nav_content):
            self.warnings['kindle'].append(
                f"TOC contains page numbers ({nav_href}) - remove for KDP "
                f"(reflowable content has no fixed pages)"
            )

        # Check for landmarks (EPUB3) or guide (EPUB2)
        if version.startswith('3'):
            if 'landmarks' not in nav_content.lower():
                self.warnings['kindle'].append(
                    f"No landmarks navigation in TOC ({nav_href}) - "
                    f"adding landmarks helps KDP build 'Go to' menu"
                )
        elif version.startswith('2'):
            guide = opf_root.find('.//opf:guide', self.NAMESPACES)
            if guide is None or len(guide.findall('.//opf:reference', self.NAMESPACES)) == 0:
                self.warnings['kindle'].append(
                    "No <guide> element in OPF - adding guide references helps KDP build navigation"
                )

    def _kdp_check_unsupported_html(self, epub: zipfile.ZipFile, manifest: Dict):
        """Check for HTML elements not supported by Amazon KDP"""
        # Check manifest for unsupported media types
        media_types_unsupported = ('audio/mpeg', 'audio/mp4', 'video/mp4', 'video/h264')
        for item_id, item_info in manifest.items():
            if item_info['media_type'] in media_types_unsupported:
                self.issues['kindle'].append(
                    f"Audio/video content '{item_info['href']}' not supported on KDP"
                )

        for item_id, item_info in manifest.items():
            if item_info['media_type'] not in ('application/xhtml+xml', 'text/html'):
                continue

            content = self._read_file_cached(epub, item_info['href'])
            if not content:
                continue

            href = item_info['href']
            content_clean = self.RE_COMMENT.sub('', content)

            # Form elements, canvas, iframe
            reported_tags = set()
            for match in self.RE_FORM_ELEMENTS.finditer(content_clean):
                tag = match.group(1).lower()
                if tag not in reported_tags:
                    reported_tags.add(tag)
                    self.issues['kindle'].append(
                        f"Unsupported <{tag}> element in '{href}' - not supported by KDP"
                    )

            # Audio/video HTML tags
            for match in self.RE_AUDIO_VIDEO_HTML.finditer(content_clean):
                tag = match.group(1).lower()
                if tag not in reported_tags:
                    reported_tags.add(tag)
                    self.issues['kindle'].append(
                        f"Unsupported <{tag}> element in '{href}' - not supported by KDP"
                    )

            # Script tags
            if self.RE_SCRIPT_TAG.search(content_clean):
                self.issues['kindle'].append(
                    f"JavaScript in '{href}' - scripts are stripped by KDP processing"
                )

            # MathML
            if 'mathml' in item_info.get('properties', '').lower() or '<math' in content_clean.lower():
                self.issues['kindle'].append(
                    f"MathML content in '{href}' - not supported by KDP Enhanced Typesetting"
                )

    def _kdp_check_css_restrictions(self, epub: zipfile.ZipFile, manifest: Dict):
        """Check CSS restrictions for Amazon KDP"""
        css_files = [item for item in manifest.values() if item['media_type'] == 'text/css']

        for css_file in css_files:
            href = css_file['href']
            content = self._read_file_cached(epub, href)
            if not content:
                continue

            clean = self.RE_CSS_COMMENT.sub('', content)

            # Fixed font-size units (px/pt)
            if self.RE_CSS_FONT_SIZE_FIXED.search(clean):
                self.warnings['kindle'].append(
                    f"Fixed font-size units (px/pt) in '{href}' - use relative units (em/rem/%) for KDP"
                )

            # Negative margins
            if self.RE_CSS_NEGATIVE_MARGIN.search(clean):
                self.warnings['kindle'].append(
                    f"Negative margin values in '{href}' - may cause clipped content on Kindle devices"
                )

            # max-width/max-height
            if self.RE_CSS_MAX_DIM.search(clean):
                self.warnings['kindle'].append(
                    f"max-width/max-height in '{href}' - may be ignored by KDP rendering engine"
                )

            # Unsupported pseudo-classes
            if self.RE_CSS_PSEUDO_UNSUPPORTED.search(clean):
                self.warnings['kindle'].append(
                    f"Unsupported CSS pseudo-classes (:nth-child/:first-child/:visited) in '{href}'"
                )

            # Pseudo-elements
            if self.RE_CSS_PSEUDO_ELEMENT.search(clean):
                self.warnings['kindle'].append(
                    f"CSS pseudo-elements (::before/::after) in '{href}' - limited KDP support"
                )

            # Body font-family override
            if self.RE_CSS_BODY_FONT_OVERRIDE.search(clean):
                self.warnings['kindle'].append(
                    f"body font-family override in '{href}' - may prevent reader font selection on Kindle"
                )

    def _kdp_check_enhanced_typesetting(self, epub: zipfile.ZipFile, manifest: Dict):
        """Check for patterns that break Amazon KDP Enhanced Typesetting"""
        for item_id, item_info in manifest.items():
            if item_info['media_type'] not in ('application/xhtml+xml', 'text/html'):
                continue

            content = self._read_file_cached(epub, item_info['href'])
            if not content:
                continue

            href = item_info['href']

            # Base64-encoded images
            if self.RE_BASE64_IMAGE.search(content):
                self.warnings['kindle'].append(
                    f"Base64-encoded image in '{href}' - disables Enhanced Typesetting; use external image files"
                )

            # SVG with namespace prefixes (e.g., svg:rect instead of rect)
            if 'svg:' in content.lower() and '<svg' in content.lower():
                self.warnings['kindle'].append(
                    f"SVG namespace prefixes in '{href}' - may break KDP rendering; use default namespace"
                )

            # Float inside table cells (inline styles)
            if re.search(r'<t[dh][^>]*style=[^>]*float\s*:', content, re.IGNORECASE):
                self.warnings['kindle'].append(
                    f"Float in table cells in '{href}' - breaks Enhanced Typesetting"
                )

        # Check CSS for enhanced typesetting breakers
        css_files = [item for item in manifest.values() if item['media_type'] == 'text/css']
        for css_file in css_files:
            href = css_file['href']
            content = self._read_file_cached(epub, href)
            if not content:
                continue

            clean = self.RE_CSS_COMMENT.sub('', content)

            # linear-gradient
            if self.RE_CSS_LINEAR_GRADIENT.search(clean):
                self.warnings['kindle'].append(
                    f"CSS linear-gradient() in '{href}' - not supported by KDP Enhanced Typesetting"
                )

            # caption-side: bottom
            if self.RE_CSS_CAPTION_SIDE.search(clean):
                self.warnings['kindle'].append(
                    f"caption-side:bottom in '{href}' - not supported by KDP Enhanced Typesetting"
                )

    def _kdp_check_image_requirements(self, epub: zipfile.ZipFile, manifest: Dict):
        """Check image requirements for Amazon KDP"""
        for item_id, item_info in manifest.items():
            media_type = item_info['media_type']
            href = item_info['href']

            # TIFF not supported
            if media_type == 'image/tiff' or href.lower().endswith(('.tiff', '.tif')):
                self.issues['kindle'].append(
                    f"TIFF image '{href}' not supported by KDP - convert to JPEG or PNG"
                )

            # Animated GIF detection
            if media_type == 'image/gif':
                try:
                    gif_data = epub.read(href)
                    if b'NETSCAPE2.0' in gif_data or b'NETSCAPE 2.0' in gif_data:
                        self.warnings['kindle'].append(
                            f"Animated GIF '{href}' - KDP displays only first frame"
                        )
                except (KeyError, IOError):
                    pass

        # Check alt text on images in HTML content
        missing_alt_count = 0
        for item_id, item_info in manifest.items():
            if item_info['media_type'] not in ('application/xhtml+xml', 'text/html'):
                continue
            content = self._read_file_cached(epub, item_info['href'])
            if not content:
                continue
            for match in self.RE_IMG_ALT.finditer(content):
                img_tag = match.group(0)
                if 'alt=' not in img_tag.lower():
                    missing_alt_count += 1

        if missing_alt_count > 0:
            self.warnings['kindle'].append(
                f"{missing_alt_count} image(s) missing alt text - KDP recommends alt attributes for accessibility"
            )

    def _kdp_check_font_rules(self, manifest: Dict):
        """Check font requirements for Amazon KDP"""
        for item_id, item_info in manifest.items():
            href = item_info['href']
            if href.lower().endswith('.woff') or item_info['media_type'] == 'font/woff':
                self.issues['kindle'].append(
                    f"WOFF font '{href}' not supported by KDP - use TTF or OTF format"
                )
            elif href.lower().endswith('.woff2') or item_info['media_type'] == 'font/woff2':
                self.issues['kindle'].append(
                    f"WOFF2 font '{href}' not supported by KDP - use TTF or OTF format"
                )

    def _kdp_check_content_quality(self, epub: zipfile.ZipFile, manifest: Dict):
        """Check content quality issues for Amazon KDP"""
        excessive_nbsp_files = []

        for item_id, item_info in manifest.items():
            if item_info['media_type'] not in ('application/xhtml+xml', 'text/html'):
                continue

            content = self._read_file_cached(epub, item_info['href'])
            if not content:
                continue

            href = item_info['href']

            # Excessive non-breaking spaces
            if self.RE_NBSP_EXCESSIVE.search(content):
                excessive_nbsp_files.append(href)

        if excessive_nbsp_files:
            self.warnings['kindle'].append(
                f"Excessive non-breaking spaces in {len(excessive_nbsp_files)} file(s) - "
                f"use CSS margins/padding for spacing instead"
            )

        # Check CSS for body-level bold/italic and forced colors
        css_files = [item for item in manifest.values() if item['media_type'] == 'text/css']
        color_file_count = 0
        for css_file in css_files:
            content = self._read_file_cached(epub, css_file['href'])
            if not content:
                continue
            clean = self.RE_CSS_COMMENT.sub('', content)
            href = css_file['href']

            if self.RE_CSS_BODY_BOLD.search(clean):
                self.warnings['kindle'].append(
                    f"body {{ font-weight: bold }} in '{href}' - forces all text bold, not recommended for KDP"
                )
            if self.RE_CSS_BODY_ITALIC.search(clean):
                self.warnings['kindle'].append(
                    f"body {{ font-style: italic }} in '{href}' - forces all text italic, not recommended for KDP"
                )

            # Count files with forced text colors
            if self.RE_CSS_COLOR_FORCE.search(clean):
                color_file_count += 1

        if color_file_count > 0:
            self.warnings['kindle'].append(
                f"Forced text colors in {color_file_count} CSS file(s) - "
                f"may be invisible in Kindle dark mode"
            )

    def _generate_report(self) -> Dict:
        """Generate final validation report"""
        # Generate critical issues summary
        critical_summary = self._generate_critical_summary()
        
        return {
            'info': self.info,
            'issues': self.issues,
            'warnings': self.warnings,
            'critical_summary': critical_summary
        }
    
    def _generate_critical_summary(self) -> Dict:
        """Generate summary of critical platform-specific issues"""
        summary = {
            'apple_books': [],
            'pocketbook': [],
            'kindle': [],
            'general': []
        }
        
        # Check for Apple Books blockers
        apple_issues = self.issues['apple_books']
        if any('entity' in issue.lower() for issue in apple_issues):
            summary['apple_books'].append("HTML entity errors prevent full rendering")
        if any('xml parsing' in issue.lower() for issue in apple_issues):
            summary['apple_books'].append("XML parsing errors stop content display")
        
        # Check for PocketBook blockers
        pb_issues = self.issues['pocketbook']
        transform_count = len([i for i in pb_issues if 'CSS transform' in i and 'text-transform' not in i])
        if transform_count > 0:
            summary['pocketbook'].append(
                f"CSS transforms ({transform_count} found) STOP rendering after ~20 pages"
            )
        
        # Check for large margin issues
        margin_count = len([i for i in pb_issues if 'Large margin' in i])
        if margin_count > 0:
            summary['pocketbook'].append(
                f"Large margin values ({margin_count} found) cause mixed/unreadable text layout"
            )
        
        # Check for InkBook blockers (similar to PocketBook)
        ib_issues = self.issues['inkbook']
        if len(ib_issues) > 0:
            # InkBook shares similar issues with PocketBook
            pass

        # Check for KDP blockers
        kindle_issues = self.issues['kindle']
        if any('cover' in i.lower() and ('requires' in i.lower() or 'too small' in i.lower()
               or 'not accepted' in i.lower()) for i in kindle_issues):
            summary['kindle'].append("Cover image issues may prevent KDP publishing")
        if any('dc:identifier' in i.lower() for i in kindle_issues):
            summary['kindle'].append("Missing required dc:identifier metadata")
        if any('table of contents' in i.lower() for i in kindle_issues):
            summary['kindle'].append("Missing table of contents required by KDP")
        unsupported = [i for i in kindle_issues
                       if 'unsupported' in i.lower() or 'not supported' in i.lower()]
        if unsupported:
            summary['kindle'].append(
                f"Unsupported content ({len(unsupported)} issues) may be stripped or cause rejection"
            )

        # Check for general critical issues
        gen_issues = self.issues['general']
        entity_count = len([i for i in gen_issues if 'entity' in i.lower() and 'nbsp' in i.lower()])
        if entity_count > 0:
            summary['general'].append(f"HTML entity errors ({entity_count}) affect all readers")
        
        return summary


def print_report(report: Dict, output_file=None):
    """Pretty print the validation report and optionally save to file"""
    
    # Capture output to a string buffer first
    import io
    output = io.StringIO()
    
    # Track which explanations have been shown
    shown_explanations = set()
    
    # Explanations for common errors
    EXPLANATIONS = {
        r"Undeclared entity": "Reference: HTML entities like &nbsp; must be declared in XML/XHTML. Use &#160; instead. See: https://www.w3.org/TR/xhtml1/dtds.html#a_dtd_Special_pre",
        r"CSS transform detected": "Reference: CSS transform property (rotate, scale, translate - NOT text-transform) causes rendering engines to crash on some e-ink readers (PocketBook, InkBook).",
        r"XML Parsing Error": "Reference: EPUB content must be valid XML/XHTML. Malformed XML causes parsing failures on strict readers like Apple Books. EPUB 3.3 \u00a7 2.3",
        r"Absolute positioning": "Reference: Absolute positioning breaks the reflowable nature of EPUBs and causes overlapping text on different screen sizes.",
        r"Viewport units": "Reference: Viewport units (vw, vh) are not consistently supported across all e-reader rendering engines.",
        r"Missing image": "Reference: All resources listed in the OPF manifest must exist in the EPUB package. Check if file exists or manifest declares wrong path. EPUB 3.3 \u00a7 3.3",
        r"Inline styles": "Reference: Inline styles are difficult to override by user settings and may not be supported by all reading systems.",
        r"Scripted content": "Reference: Scripting is often disabled for security or performance on e-readers. See EPUB 3.2 Spec \u00a7 2.4.",
        r"Fixed layout": "Reference: Fixed layout books do not allow text resizing and are often incompatible with small e-ink screens. EPUB 3.3 \u00a7 6.2",
        r"Mimetype|mimetype": "Reference: The mimetype file must be the first file in the ZIP archive and contain exactly 'application/epub+zip'. EPUB OCF 3.0 \u00a7 3.3",
        r"container\.xml": "Reference: META-INF/container.xml is required to locate the OPF file. EPUB OCF 3.0 \u00a7 3.5.1",
        r"DRM/Encryption": "Reference: Encrypted EPUBs require specific reader support and may limit distribution options. EPUB OCF 3.0 \u00a7 4",
        r"SVG image": "Reference: SVG support varies; some e-readers convert to raster or have limited support. EPUB 3.3 \u00a7 3.4.4",
        r"WOFF.*font": "Reference: OpenType/TrueType fonts have wider support than WOFF/WOFF2. EPUB 3.3 \u00a7 3.4.3",
        r"MathML": "Reference: MathML support requires MathML-capable reading system. EPUB 3.3 \u00a7 6.3",
        r"Large margin value": "Note: Empirical finding on PocketBook readers - margins >5em cause rendering glitches and mixed text layout.",
        r"toc\.ncx": "Reference: EPUB 2.0.1 requires NCX file for navigation. EPUB 2.0.1 \u00a7 2.4.1",
        r"navigation document": "Reference: EPUB 3 requires navigation document with properties='nav'. EPUB 3.3 \u00a7 5.4",
        r"dc:language": "Reference: Language metadata is REQUIRED in EPUB. Use BCP 47 codes (e.g., 'en', 'en-US'). EPUB 3.3 \u00a7 4.2.2",
        r"Spine references": "Reference: All spine itemrefs must reference valid manifest items. EPUB 3.3 \u00a7 4.3",
        r"Duplicate ID": "Reference: XML IDs must be unique across all documents. XML 1.0 \u00a7 3.3.1, EPUB 3.3 \u00a7 3.3.2",
        r"Broken link": "Reference: All internal links must reference valid files and IDs. EPUB 3.3 \u00a7 3.3.2",
        r"cover image|cover-image": "Reference: Cover image should be designated with properties='cover-image' in manifest. EPUB 3.3 \u00a7 3.2",
        r"KDP REQUIRES a cover": "Reference: Amazon KDP requires a cover image of at least 625x1000px (ideal 1600x2560px). JPEG or PNG only. See: https://kdp.amazon.com/en_US/help/topic/G200645690",
        r"dc:identifier": "Reference: A unique book identifier (ISBN, ASIN, or UUID) is required for Amazon KDP publishing. Add <dc:identifier> to your OPF metadata.",
        r"Enhanced Typesetting": "Reference: Amazon Enhanced Typesetting provides improved typography but is disabled by certain CSS/HTML patterns. See: https://kdp.amazon.com/en_US/help/topic/G202187570",
        r"KDP REQUIRES a functional TOC": "Reference: Amazon KDP requires a functional, linked table of contents for all e-books.",
        r"TIFF image": "Reference: TIFF images are not supported by Amazon KDP. Convert to JPEG or PNG before uploading.",
        r"Fixed font-size units": "Reference: Fixed font sizes (px/pt) prevent users from adjusting text size on Kindle. Use relative units (em, rem, %).",
        r"not supported by KDP": "Note: Since March 2025, Amazon KDP accepts EPUB directly (MOBI uploads are no longer accepted). Ensure your EPUB meets KDP requirements before uploading."
    }
    
    def log(msg=""):
        print(msg)
        output.write(msg + "\n")

    def check_explanation(message):
        for pattern, explanation in EXPLANATIONS.items():
            if pattern in message and pattern not in shown_explanations:
                shown_explanations.add(pattern)
                log(f"     [INFO] {explanation}")

    if not report:
        log("No report generated.")
        return

    log("\n" + "="*70)
    log("EPUB VALIDATION REPORT")
    log("="*70)
    
    # Basic info
    info = report['info']
    log(f"\n[TITLE]   {info['title']}")
    log(f"[AUTHOR]  {info['author']}")
    log(f"[VERSION] {info['version']}")
    log(f"[SIZE]    {info.get('file_size_mb', 'Unknown')} MB")
    log(f"[FILES]   {info['file_count']}")
    log(f"[IMAGES]  {info['image_count']}")
    log(f"[CSS]     {info['css_count']}")
    if 'font_count' in info:
        log(f"[FONTS]   {info['font_count']}")
    if info.get('identifier'):
        log(f"[ID]      {info['identifier']}")
    if info.get('language'):
        log(f"[LANG]    {info['language']}")
    
    # Platform-specific reports
    platforms = [
        ('PC Reader', 'pc_reader'),
        ('Apple Books', 'apple_books'),
        ('Kobo', 'kobo'),
        ('PocketBook', 'pocketbook'),
        ('InkBook', 'inkbook'),
        ('Amazon KDP', 'kindle'),
        ('Android Readers', 'android')
    ]
    
    for platform_name, platform_key in platforms:
        issues = report['issues'][platform_key]
        warnings = report['warnings'][platform_key]
        
        if issues or warnings:
            log(f"\n--- {platform_name.upper()} ---")
            
            if issues:
                for issue in issues:
                    log(f"  [ERROR] {issue}")
                    check_explanation(issue)
            
            if warnings:
                for warning in warnings:
                    log(f"  [WARN]  {warning}")
                    check_explanation(warning)
    
    # General issues
    general_issues = report['issues']['general']
    general_warnings = report['warnings']['general']
    
    if general_issues or general_warnings:
        log(f"\n--- GENERAL ---")
        
        if general_issues:
            for issue in general_issues:
                log(f"  [ERROR] {issue}")
                check_explanation(issue)
        
        if general_warnings:
            for warning in general_warnings:
                log(f"  [WARN]  {warning}")
                check_explanation(warning)
    
    # Critical Issues Summary
    critical = report.get('critical_summary', {})
    has_critical = any(len(v) > 0 for v in critical.values())
    
    if has_critical:
        log("\n" + "="*70)
        log("CRITICAL ISSUES - REQUIRE IMMEDIATE ATTENTION")
        log("="*70)
        
        if critical.get('apple_books'):
            log("\nAPPLE BOOKS - Book Cannot Load Properly:")
            for issue in critical['apple_books']:
                log(f"   [CRITICAL] {issue}")
        
        if critical.get('pocketbook'):
            log("\nPOCKETBOOK - Rendering Stops Early:")
            for issue in critical['pocketbook']:
                log(f"   [CRITICAL] {issue}")
            log("   [SUGGESTION] Remove CSS transform properties from stylesheet")
            log("   [NOTE] InkBook readers have similar CSS transform issues")

        if critical.get('kindle'):
            log("\nAMAZON KDP - Publishing May Be Rejected:")
            for issue in critical['kindle']:
                log(f"   [CRITICAL] {issue}")

        if critical.get('general'):
            log("\nGENERAL - Affects Multiple Readers:")
            for issue in critical['general']:
                log(f"   [CRITICAL] {issue}")
    
    # Summary
    total_issues = sum(len(v) for v in report['issues'].values())
    total_warnings = sum(len(v) for v in report['warnings'].values())
    
    log("\n" + "="*70)
    log(f"SUMMARY: {total_issues} issues, {total_warnings} warnings")
    if has_critical:
        critical_count = sum(len(v) for v in critical.values())
        log(f"         {critical_count} CRITICAL issues requiring immediate fixes")
    log("="*70 + "\n")

    # Save to file if requested
    if output_file:
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(output.getvalue())
            print(f"\n[SUCCESS] Report saved to: {output_file}")
        except Exception as e:
            print(f"\n[ERROR] Could not save report: {e}")


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python epub_validator.py <epub_file>")
        print("\nExample: python epub_validator.py mybook.epub")
        sys.exit(1)
    
    epub_path = sys.argv[1]
    
    print(f"Validating EPUB: {epub_path}")
    
    validator = EPUBValidator(epub_path)
    report = validator.validate()
    
    if report:
        # Generate a filename based on the epub name
        output_filename = Path(epub_path).stem + "_validation_report.txt"
        print_report(report, output_file=output_filename)


if __name__ == '__main__':
    main()
