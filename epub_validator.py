#!/usr/bin/env python3
"""
EPUB Validator - Assess EPUB files for compatibility issues across different readers
Supports: Standard PC readers, Apple Books, PocketBook, and Kindle

Version: 1.3
Last Updated: 2025-12-03

CHANGELOG:
- v1.3: Added NCX/TOC validation, duplicate ID checking, broken link validation
        Added language metadata validation (required by spec)
        Added cover image validation with properties check
        Added spine reference validation
        Fixed false positives: DOCTYPE entity detection, JavaScript detection
        Refined inline styles and large image warnings to reduce noise
        Enhanced all error messages with EPUB spec references
- v1.2: Added detection of large margin values that break PocketBook layout
        Enhanced critical summary to include margin layout issues
        Improved PocketBook compatibility checking
- v1.1: Fixed false positive detection of text-transform as CSS transform
        Reduced duplicate entity error reporting
        Improved accuracy of platform-specific issue detection
- v1.0: Initial release
"""

import os
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Set, Tuple
import re
from collections import defaultdict


class EPUBValidator:
    """Validates EPUB files and reports platform-specific issues"""
    
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
            'file_count': 0,
            'image_count': 0,
            'css_count': 0
        }
        
    def validate(self) -> Dict:
        """Run all validation checks"""
        if not self.epub_path.exists():
            print(f"Error: File '{self.epub_path}' does not exist")
            return None
            
        if not zipfile.is_zipfile(self.epub_path):
            print(f"Error: '{self.epub_path}' is not a valid ZIP/EPUB file")
            return None
        
        try:
            with zipfile.ZipFile(self.epub_path, 'r') as epub:
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
                self._check_kindle_issues(opf_root, manifest, spine)
                self._check_kobo_issues(opf_root, manifest)
                self._check_inkbook_issues(opf_root, manifest)
                self._check_android_issues(opf_root, manifest)
                
        except Exception as e:
            self.issues['general'].append(f"Error processing EPUB: {str(e)}")
        
        return self._generate_report()
    
    def _check_mimetype(self, epub: zipfile.ZipFile):
        """Check mimetype file exists and is correct"""
        try:
            mimetype = epub.read('mimetype').decode('utf-8').strip()
            if mimetype != 'application/epub+zip':
                self.issues['general'].append(
                    f"Invalid mimetype: '{mimetype}' (should be 'application/epub+zip')"
                )
        except KeyError:
            self.issues['general'].append("Missing 'mimetype' file")
    
    def _check_container(self, epub: zipfile.ZipFile):
        """Check META-INF/container.xml exists"""
        try:
            epub.read('META-INF/container.xml')
        except KeyError:
            self.issues['general'].append("Missing 'META-INF/container.xml' file")
    
    def _get_opf_path(self, epub: zipfile.ZipFile) -> str:
        """Get the path to the OPF file from container.xml"""
        try:
            container_xml = epub.read('META-INF/container.xml').decode('utf-8')
            container_root = ET.fromstring(container_xml)
            
            rootfile = container_root.find('.//container:rootfile', self.NAMESPACES)
            if rootfile is not None:
                return rootfile.get('full-path')
        except Exception as e:
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
                # Validate BCP 47 format (basic check)
                if not re.match(r'^[a-z]{2,3}(-[A-Z]{2,4})?(-[a-z]{4})?$', lang_code):
                    self.warnings['general'].append(
                        f"Invalid language code '{lang_code}' - should be BCP 47 format (e.g., 'en', 'en-US')"
                    )
                self.info['language'] = lang_code
        
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
                
                try:
                    content = epub.read(href).decode('utf-8', errors='ignore')
                    
                    # Check for HTML entities without proper declaration
                    self._check_html_entities(content, href)
                    
                    # Check for XML/XHTML validity issues
                    self._check_xhtml_validity(content, href)
                    
                    # Check for common issues
                    # Remove HTML comments first to avoid false positives
                    content_no_comments = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
                    if re.search(r'<script[>\s]', content_no_comments, re.IGNORECASE):
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
                    
                except KeyError:
                    self.issues['general'].append(f"Referenced file not found: '{href}'")
                except Exception as e:
                    self.warnings['general'].append(
                        f"Error reading '{href}': {str(e)}"
                    )
        
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
            large_margin_match = re.search(r'margin[^:]*:\s*(\d+(?:\.\d+)?)(em|rem)', line, re.IGNORECASE)
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
            if re.search(r'\d+vw|\d+vh|\d+vmin|\d+vmax', line):
                self.warnings['pocketbook'].append(
                    f"{file_path} (line {line_num}): Viewport units may not work correctly"
                )
            
            # Check for transforms
            if 'transform:' in line or 'transform :' in line:
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
            except:
                pass
        
        # Track which files reference missing images
        if missing_images:
            self._find_image_references(epub, manifest, missing_images)
    
    def _get_image_dimensions(self, img_data: bytes, media_type: str) -> Tuple:
        """Extract image dimensions from JPEG or PNG data"""
        try:
            if media_type == 'image/png' and len(img_data) > 24:
                # PNG dimensions are at bytes 16-24
                import struct
                width, height = struct.unpack('>II', img_data[16:24])
                return width, height
            elif media_type == 'image/jpeg':
                # Basic JPEG dimension extraction
                import struct
                i = 0
                while i < len(img_data) - 9:
                    if img_data[i] == 0xFF:
                        if img_data[i+1] in [0xC0, 0xC1, 0xC2]:
                            height, width = struct.unpack('>HH', img_data[i+5:i+9])
                            return width, height
                    i += 1
        except:
            pass
        return None, None
    
    def _find_image_references(self, epub: zipfile.ZipFile, manifest: Dict, missing_images: Set[str]):
        """Find which XHTML files reference missing images"""
        for item_id, item_info in manifest.items():
            if item_info['media_type'] in ['application/xhtml+xml', 'text/html']:
                try:
                    content = epub.read(item_info['href']).decode('utf-8', errors='ignore')
                    for missing_img in missing_images:
                        img_name = missing_img.split('/')[-1]
                        if img_name in content or missing_img in content:
                            self.issues['general'].append(
                                f"File '{item_info['href']}' references missing image '{missing_img}'"
                            )
                except:
                    pass
    
    def _validate_css(self, epub: zipfile.ZipFile, manifest: Dict):
        """Validate CSS files for platform compatibility"""
        import re
        
        css_files = [item for item in manifest.values() if item['media_type'] == 'text/css']
        
        for css_file in css_files:
            href = css_file['href']
            try:
                with epub.open(href) as f:
                    content = f.read().decode('utf-8', errors='ignore')
                    
                # Remove comments to avoid false positives
                # This regex handles /* ... */ style comments
                clean_content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
                
                lines = content.splitlines() # Keep original for line numbers
                
                # Check for PocketBook/InkBook issues (CSS Transforms)
                # Note: text-transform is NOT the same as transform!
                # text-transform: uppercase/lowercase/capitalize - SAFE
                # transform: rotate/scale/translate - BREAKS RENDERING
                
                # Look for transform property but exclude text-transform
                transform_pattern = re.compile(r'(?<!text-)transform\s*:', re.IGNORECASE)
                if transform_pattern.search(clean_content):
                    for i, line in enumerate(lines, 1):
                        # Check if line is not commented out (simple check)
                        if transform_pattern.search(line) and not line.strip().startswith('/*'):
                            msg = f"CSS transform detected (stops rendering on PocketBook/InkBook): {line.strip()[:50]}..."
                            self.issues['pocketbook'].append(f"{href} (line {i}): {msg}")
                            self.issues['inkbook'].append(f"{href} (line {i}): {msg}")

                # Check for absolute positioning (often bad for reflowable)
                if 'position: absolute' in clean_content or 'position:absolute' in clean_content:
                    self.warnings['general'].append(
                        f"{href}: Absolute positioning detected (may break reflowable layout)"
                    )
                    
            except Exception as e:
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
                try:
                    content = epub.read(item_info['href']).decode('utf-8', errors='ignore')
                    
                    # Find all id attributes using regex (more reliable than XML parsing for malformed docs)
                    for match in re.finditer(r'\\bid\\s*=\\s*["\']([^"\']+)["\']', content, re.IGNORECASE):
                        elem_id = match.group(1)
                        all_ids[elem_id].append(item_info['href'])
                except:
                    pass
        
        # Check for duplicates across files
        for elem_id, files in all_ids.items():
            if len(files) > 1:
                self.issues['general'].append(
                    f"Duplicate ID '{elem_id}' found in multiple files: {', '.join(files[:3])}\"{'...' if len(files) > 3 else ''}\" (XML 1.0 \u00a7 3.3.1)"
                )
    
    def _validate_links(self, epub: zipfile.ZipFile, manifest: Dict):
        """Validate all internal links and references"""
        # Build set of valid files
        valid_files = {item['href'] for item in manifest.values()}
        
        # Collect all IDs per file
        file_ids = defaultdict(set)  # file -> set of IDs
        for item_id, item_info in manifest.items():
            if item_info['media_type'] in ['application/xhtml+xml', 'text/html']:
                try:
                    content = epub.read(item_info['href']).decode('utf-8', errors='ignore')
                    for match in re.finditer(r'\\bid\\s*=\\s*["\']([^"\']+)["\']', content, re.IGNORECASE):
                        elem_id = match.group(1)
                        file_ids[item_info['href']].add(elem_id)
                except:
                    pass
        
        # Validate links
        for item_id, item_info in manifest.items():
            if item_info['media_type'] in ['application/xhtml+xml', 'text/html']:
                try:
                    content = epub.read(item_info['href']).decode('utf-8', errors='ignore')
                    
                    # Find all href attributes
                    for match in re.finditer(r'href\\s*=\\s*["\']([^"\']+)["\']', content, re.IGNORECASE):
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
                except:
                    pass
    
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
                    self.warnings['kindle'].append(
                        f"WOFF font '{href}' not supported on older Kindle devices"
                    )
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
    
    def _check_kindle_issues(self, opf_root: ET.Element, manifest: Dict, spine: List):
        """Check for Kindle specific issues"""
        # Kindle has the most restrictions
        
        # Note: EPUB 3 is acceptable, Kindle can handle it with conversion
        
        # Check for audio/video
        media_types = ['audio/mpeg', 'audio/mp4', 'video/mp4', 'video/h264']
        for item_id, item_info in manifest.items():
            if item_info['media_type'] in media_types:
                self.issues['kindle'].append(
                    f"Audio/Video content '{item_info['href']}' not supported on Kindle (requires conversion)"
                )
        
        # Check for complex tables
        # Would require parsing XHTML - adding as general note
        self.warnings['kindle'].append(
            "Complex tables may not render well - verify after conversion to MOBI/AZW3"
        )
        
        # Kindle doesn't support EPUBs directly
        self.issues['kindle'].append(
            "Kindle devices require conversion from EPUB to MOBI/AZW3 format"
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
        r"cover image|cover-image": "Reference: Cover image should be designated with properties='cover-image' in manifest. EPUB 3.3 \u00a7 3.2"
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
    
    # Platform-specific reports
    platforms = [
        ('PC Reader', 'pc_reader'),
        ('Apple Books', 'apple_books'),
        ('Kobo', 'kobo'),
        ('PocketBook', 'pocketbook'),
        ('InkBook', 'inkbook'),
        ('Kindle', 'kindle'),
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
