# EPUB Validator

A comprehensive EPUB validation tool that checks e-book files for compatibility issues across different reading platforms and devices.

[![Version](https://img.shields.io/badge/version-1.3-blue.svg)](https://github.com/XClassicPeter/epub_validator)
[![Python](https://img.shields.io/badge/python-3.7+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)

## Features

- **Multi-Platform Validation**: Tests compatibility with PC readers (Calibre, Adobe Digital Editions), Apple Books, Kobo, PocketBook, InkBook, Kindle, and Android readers
- **EPUB 2 & 3 Support**: Validates both EPUB 2.0.1 and EPUB 3.x specifications
- **Comprehensive Checks**: 
  - Structural validation (mimetype, container.xml, OPF package)
  - Navigation validation (NCX for EPUB 2, nav document for EPUB 3)
  - Content validation (XHTML/HTML, CSS, images, fonts)
  - Link validation (internal links, fragment identifiers, broken references)
  - ID uniqueness across documents
  - Metadata validation (required language, cover image)
  - Platform-specific issues (CSS transforms on e-ink, entity errors on Apple Books)
- **Detailed Reports**: Line-by-line error reporting with EPUB specification references
- **No Dependencies**: Uses only Python standard library

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Understanding EPUB Format](#understanding-epub-format)
- [Platform Rendering Differences](#platform-rendering-differences)
- [Interpreting Reports](#interpreting-reports)
- [Common Issues](#common-issues)
- [Contributing](#contributing)
- [License](#license)

## Installation

### Requirements

- Python 3.7 or higher
- No external dependencies required

### Install

```bash
# Clone the repository
git clone https://github.com/XClassicPeter/epub_validator.git
cd epub_validator

# Make executable (optional)
chmod +x epub_validator.py
```

## Quick Start

```bash
# Validate an EPUB file
python3 epub_validator.py mybook.epub

# The report is automatically saved as mybook_validation_report.txt
```

### Example Output

```
==================================================
EPUB VALIDATION REPORT
==================================================

[TITLE]   My Book Title
[AUTHOR]  Author Name
[VERSION] 3.0
[SIZE]    2.45 MB
[FILES]   42
[IMAGES]  15
[CSS]     3

--- APPLE BOOKS ---
  [ERROR] OEBPS/chapter1.xhtml (line 198): Undeclared entity 'nbsp' - 
          Replace &nbsp; with &#160; or add proper DOCTYPE
     [INFO] Reference: HTML entities like &nbsp; must be declared in XML/XHTML...

--- POCKETBOOK ---
  [ERROR] OEBPS/styles/main.css (line 45): CSS transform detected 
          (stops rendering on PocketBook/InkBook)

==================================================
CRITICAL ISSUES - REQUIRE IMMEDIATE ATTENTION
==================================================

APPLE BOOKS - Book Cannot Load Properly:
   [CRITICAL] HTML entity errors prevent full rendering

==================================================
SUMMARY: 3 issues, 5 warnings
         1 CRITICAL issues requiring immediate fixes
==================================================
```

## Understanding EPUB Format

### What is EPUB?

EPUB (Electronic Publication) is an open standard for digital books maintained by the W3C. It's essentially a ZIP archive containing HTML/XHTML content, images, CSS, and metadata.

### EPUB Structure

```
mybook.epub (ZIP file)
├── mimetype                          # Must be first file, uncompressed
├── META-INF/
│   ├── container.xml                # Points to OPF file location
│   └── encryption.xml               # Optional: font obfuscation/DRM
├── OEBPS/                            # Content directory (name varies)
│   ├── content.opf                  # Package document (manifest/spine/metadata)
│   ├── toc.ncx                      # EPUB 2 navigation (optional in EPUB 3)
│   ├── nav.xhtml                    # EPUB 3 navigation document
│   ├── Text/
│   │   ├── chapter1.xhtml
│   │   ├── chapter2.xhtml
│   │   └── ...
│   ├── Styles/
│   │   └── stylesheet.css
│   ├── Images/
│   │   ├── cover.jpg
│   │   └── ...
│   └── Fonts/
│       └── ...
```

### Key Components

#### 1. Mimetype File
- **Purpose**: Identifies the file as an EPUB
- **Content**: Exactly `application/epub+zip`
- **Requirement**: Must be first file in ZIP, stored uncompressed
- **Spec**: EPUB OCF 3.0 § 3.3

#### 2. Container.xml
- **Location**: `META-INF/container.xml`
- **Purpose**: Points to the OPF package document
- **Example**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
```
- **Spec**: EPUB OCF 3.0 § 3.5.1

#### 3. OPF Package Document
- **Purpose**: Central manifest listing all files, reading order, and metadata
- **Contains**:
  - **Metadata**: Title, author, language (required), ISBN, etc.
  - **Manifest**: All files in the EPUB with unique IDs
  - **Spine**: Reading order (references manifest IDs)
  - **Guide** (EPUB 2 only, deprecated in EPUB 3)

**Example**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>My Book</dc:title>
    <dc:creator>Author Name</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier id="bookid">urn:uuid:12345</dc:identifier>
    <meta property="dcterms:modified">2025-12-03T10:00:00Z</meta>
  </metadata>
  
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="chapter1" href="Text/chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="cover" href="Images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>
    <item id="css" href="Styles/style.css" media-type="text/css"/>
  </manifest>
  
  <spine>
    <itemref idref="cover"/>
    <itemref idref="chapter1"/>
  </spine>
</package>
```
- **Spec**: EPUB 3.3 § 4

#### 4. Navigation Documents

**EPUB 2**: `toc.ncx` (NCX file)
- XML format with hierarchical navigation
- Required in EPUB 2.0.1
- Spec: EPUB 2.0.1 § 2.4.1

**EPUB 3**: `nav.xhtml` (XHTML with `epub:type="toc"`)
- HTML5-based navigation
- Must be in manifest with `properties="nav"`
- Can include multiple navigation types (TOC, landmarks, page-list)
- Spec: EPUB 3.3 § 5.4

#### 5. Content Documents
- **Format**: XHTML 1.1 (EPUB 2) or HTML5 (EPUB 3)
- **Requirements**: 
  - Valid XML (well-formed)
  - Unique IDs within and across files
  - Proper DOCTYPE declaration for entity usage
- **Common Issues**:
  - HTML entities (`&nbsp;`) without DTD declaration → Apple Books errors
  - Malformed XML → Parsing failures
  - Missing closing tags → Rendering problems

### EPUB 2 vs EPUB 3

| Feature | EPUB 2.0.1 | EPUB 3.x |
|---------|------------|----------|
| Content Format | XHTML 1.1 | HTML5 |
| Navigation | NCX (toc.ncx) | Nav document (nav.xhtml) |
| Metadata | Dublin Core | Dublin Core + EPUB 3 properties |
| Media | Images, basic fonts | Audio, video, interactive content |
| Accessibility | Limited | Comprehensive (ARIA, semantic inflection) |
| MathML | Limited | Full support |
| Scripting | Not standardized | JavaScript support (limited in practice) |
| CSS | CSS 2.1 subset | CSS 3 (varies by reader) |

**Recommendation**: Use EPUB 3 for new publications. Most modern readers support EPUB 3, and it provides better accessibility and features.

## Platform Rendering Differences

Different e-reader platforms have varying levels of EPUB support. Understanding these differences helps create compatible e-books.

### PC Readers (Calibre, Adobe Digital Editions)

**Support Level**: ⭐⭐⭐⭐⭐ Excellent

- **Rendering Engine**: WebKit-based or similar
- **Strengths**:
  - Full EPUB 3 support
  - Most CSS 3 features work
  - Complex layouts supported
  - JavaScript enabled (in some readers)
- **Limitations**: Very few
- **Best For**: Development, testing, complex layouts

### Apple Books (iOS, macOS)

**Support Level**: ⭐⭐⭐⭐⭐ Excellent (but strict)

- **Rendering Engine**: WebKit
- **Strengths**:
  - Excellent EPUB 3 support
  - High-quality typography
  - Fixed layout support
  - Interactive widgets
- **Critical Issues**:
  - **Extremely strict XML parsing**: Undeclared HTML entities cause complete rendering failure
  - **Solution**: Replace `&nbsp;` with `&#160;`, or use proper XHTML DTD
- **Spec Compliance**: Very strict, catches most errors
- **Best For**: High-quality typography, fixed layout books

**Common Errors**:
```xml
<!-- WRONG - Causes Apple Books to fail -->
<p>Hello&nbsp;world</p>

<!-- CORRECT - Works everywhere -->
<p>Hello&#160;world</p>

<!-- ALSO CORRECT - With proper DOCTYPE -->
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
  <body><p>Hello&nbsp;world</p></body>
</html>
```

### Kobo

**Support Level**: ⭐⭐⭐⭐ Very Good

- **Rendering Engine**: Custom (WebKit-based)
- **Strengths**:
  - Good EPUB 3 support
  - Kepub enhancements (proprietary format)
  - Good typography
  - CSS support similar to PC readers
- **Limitations**:
  - Some advanced CSS features may not work
  - Fixed layout support varies by device
- **Best For**: General trade books, reflowable content

### PocketBook

**Support Level**: ⭐⭐⭐ Good (with critical limitations)

- **Rendering Engine**: Custom (e-ink optimized)
- **Strengths**:
  - Good basic EPUB support
  - Handles most standard layouts
  - Multiple format support
- **Critical Issues**:
  - **CSS transforms CRASH rendering**: Books stop displaying after ~20 pages
  - **Large margins break layout**: Margins >5em cause mixed/unreadable text
  - Absolute positioning causes issues
  - SVG support limited
  
**What to Avoid**:
```css
/* CRITICAL - BREAKS PocketBook */
.rotate {
  transform: rotate(90deg);  /* Rendering stops completely */
}

.bigmargin {
  margin-top: 8em;  /* Text becomes mixed/unreadable */
}

/* SAFE - These work fine */
.uppercase {
  text-transform: uppercase;  /* NOT the same as transform! */
}

.smallmargin {
  margin-top: 1.5em;  /* Small margins are OK */
}
```

- **Best For**: Text-heavy books without complex layouts

### InkBook (Polish e-readers)

**Support Level**: ⭐⭐⭐ Good (similar to PocketBook)

- **Rendering Engine**: Custom (e-ink optimized)
- **Issues**: Nearly identical to PocketBook
  - CSS transforms cause crashes
  - Limited SVG support
  - Complex CSS may not render
- **Best For**: Simple text layouts, standard books

### Kindle

**Support Level**: ⭐⭐⭐ Good (requires conversion)

- **Format**: Does NOT support EPUB directly
- **Requirement**: Convert to MOBI/AZW3 format
- **Tools**: Kindle Previewer, KindleGen (deprecated), Amazon KDP upload
- **Rendering Engine**: Custom (Mobi7 for old devices, KF8 for newer)
- **Limitations**:
  - EPUB 3 features lost in conversion
  - Complex CSS often simplified
  - SVG converted to raster
  - WOFF fonts not supported (TTF/OTF only)
  - Audio/video not supported
  - Fixed layout support limited
  - GIF images converted to grayscale
  - 650MB limit for email delivery

**Conversion Issues**:
- Complex tables may break
- Custom fonts may not embed correctly
- Margins and spacing may change
- CSS pseudo-elements limited

**Best Practice**: Test with Kindle Previewer before publishing

### Android Readers (Google Play Books, ReadEra, Moon+ Reader, etc.)

**Support Level**: ⭐⭐⭐⭐ Very Good (varies by app)

- **Rendering Engine**: Varies (mostly WebKit/Blink-based)
- **Strengths**:
  - Modern Android readers support most EPUB 3 features
  - Google Play Books has excellent support
  - Color displays support full image quality
- **Limitations**:
  - App-specific: each reader app has different capabilities
  - MathML support varies
  - JavaScript usually disabled
  - Audio/video support varies
- **Best For**: Color illustrations, graphic novels, general trade books

### E-ink vs LCD Rendering

**E-ink Displays** (PocketBook, InkBook, Kindle, Kobo e-readers):
- **Characteristics**:
  - Black & white (or limited grayscale)
  - Slow refresh rate
  - Limited processing power
  - Optimized for reading text
- **Implications**:
  - Animations don't work
  - Complex CSS may be simplified
  - Color images rendered in grayscale
  - Prefer simpler layouts

**LCD/OLED Displays** (Tablets, phones, PC):
- **Characteristics**:
  - Full color
  - Fast refresh
  - More processing power
- **Implications**:
  - Support more complex layouts
  - CSS effects work better
  - Full color images
  - JavaScript more likely to work

### Best Practices for Maximum Compatibility

1. **Use semantic HTML**: `<h1>`, `<p>`, `<em>`, `<strong>` instead of styled `<div>`s
2. **Keep CSS simple**: Avoid transforms, fixed positioning, complex selectors
3. **Use numeric entities**: `&#160;` instead of `&nbsp;`
4. **Test on multiple platforms**: Especially Apple Books (strictest) and PocketBook (most limitations)
5. **Validate structure**: Ensure all files exist, IDs are unique, links work
6. **Optimize images**: JPEG/PNG only, reasonable dimensions (1000-2000px for most images)
7. **Use standard fonts**: Or embed TTF/OTF (not WOFF) for broad compatibility
8. **Keep margins reasonable**: < 2em to avoid PocketBook issues
9. **Include language metadata**: Required by spec, helps reader software
10. **Provide navigation**: NCX for EPUB 2, nav document for EPUB 3

## Interpreting Reports

### Error Levels

- **[ERROR]**: Critical issue that may prevent the book from loading or rendering correctly
- **[WARN]**: Potential compatibility issue that may affect some readers
- **[CRITICAL]**: Blocking issue that prevents content from displaying on specific platforms
- **[INFO]**: Additional context and specification references

### Common Errors and Fixes

#### 1. Undeclared HTML Entities (Apple Books)

**Error**:
```
[ERROR] chapter1.xhtml (line 45): Undeclared entity 'nbsp'
```

**Fix**:
```html
<!-- Before -->
<p>Hello&nbsp;world</p>

<!-- After -->
<p>Hello&#160;world</p>
```

**Or add DOCTYPE**:
```html
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
```

#### 2. CSS Transforms (PocketBook/InkBook)

**Error**:
```
[ERROR] style.css (line 23): CSS transform detected (stops rendering)
```

**Fix**: Remove transform properties
```css
/* Before - BREAKS PocketBook */
.rotate {
  transform: rotate(45deg);
}

/* After - REMOVE or use alternatives */
/* For e-ink, transforms don't make sense anyway */
```

#### 3. Missing Navigation

**Error**:
```
[ERROR] Missing navigation document with properties='nav' (EPUB 3)
```

**Fix**: Create nav.xhtml and reference in OPF
```xml
<!-- In content.opf manifest -->
<item id="nav" href="nav.xhtml" 
      media-type="application/xhtml+xml" 
      properties="nav"/>
```

#### 4. Broken Internal Links

**Error**:
```
[ERROR] chapter1.xhtml: Broken link to 'chapter99.xhtml' (file not found)
```

**Fix**: Ensure target file exists and is in manifest, or fix the link

#### 5. Missing Language Metadata

**Error**:
```
[ERROR] Missing dc:language metadata (REQUIRED by EPUB specification)
```

**Fix**: Add to OPF metadata
```xml
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:language>en</dc:language>
</metadata>
```

## Common Issues

### Issue: Book loads in some readers but not Apple Books

**Cause**: HTML entities without DTD declaration

**Solution**: Use numeric entities (`&#160;`) or add proper XHTML DOCTYPE

### Issue: PocketBook stops showing pages after ~20 pages

**Cause**: CSS transforms in stylesheet

**Solution**: Remove all `transform:` properties (NOT `text-transform`)

### Issue: Text layout becomes scrambled on PocketBook

**Cause**: Large margin values (>5em)

**Solution**: Reduce margins to <2em or use pixel values

### Issue: Kindle rejects EPUB upload

**Cause**: Multiple issues possible
1. Invalid structure (missing mimetype, container.xml)
2. File too large (>650MB for email delivery)
3. Unsupported features (EPUB 3 advanced features)

**Solution**: Run validator, fix structural errors, convert with Kindle Previewer

### Issue: Images don't show on some readers

**Cause**: 
1. Missing files (in manifest but not in ZIP)
2. SVG images (limited support)
3. Incorrect media-type in manifest

**Solution**: Ensure files exist, use JPEG/PNG, verify manifest

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Areas for Improvement

- Accessibility metadata validation (EPUB Accessibility 1.1)
- Media overlay validation
- Semantic inflection (epub:type) validation
- Font obfuscation validation
- More comprehensive CSS validation
- Performance optimizations for large EPUBs

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Resources

### EPUB Specifications

- [EPUB 3.3 Specification](https://www.w3.org/TR/epub-33/) - Latest version
- [EPUB 3.2 Specification](https://www.w3.org/TR/epub-32/) - Previous version
- [EPUB 2.0.1 Specification](http://idpf.org/epub/201) - Legacy
- [EPUB Accessibility 1.1](https://www.w3.org/TR/epub-a11y-11/)
- [EPUB Open Container Format 3.0](https://www.w3.org/TR/epub-33/#sec-ocf)

### Tools

- [Calibre](https://calibre-ebook.com/) - E-book management and conversion
- [Sigil](https://sigil-ebook.com/) - EPUB editor
- [EPUBCheck](https://www.w3.org/publishing/epubcheck/) - Official EPUB validator
- [Kindle Previewer](https://kdp.amazon.com/en_US/help/topic/G202131170) - Test Kindle conversion

### Validators

- [EPUBCheck Online](https://www.pagina.gmbh/produkte/epub-checker/) - Official validator
- [Ace by DAISY](https://inclusivepublishing.org/toolbox/accessibility-checker/) - Accessibility checker

---

**Version**: 1.3  
**Last Updated**: December 3, 2025  
**Author**: XClassicPeter  
**Repository**: https://github.com/XClassicPeter/epub_validator
