# Changelog

All notable changes to this project will be documented in this file.

## [1.4] - 2025-12-03

### Added
- Security: ZIP bomb protection with decompression ratio limits
- Security: Path traversal prevention for all file access
- Performance: File content caching to avoid redundant reads
- Validation: Mimetype compression check per EPUB OCF spec

### Changed
- Pre-compiled regex patterns for better performance
- Improved BCP 47 language code validation
- Replaced bare except clauses with specific exceptions
- Removed always-triggered Kindle "requires conversion" noise

### Fixed
- Critical regex bugs in ID and link validation (escaped backslashes)

## [1.3] - 2025-12-03

### Added
- NCX/TOC validation
- Duplicate ID checking
- Broken link validation
- Language metadata validation (required by spec)
- Cover image validation with properties check
- Spine reference validation
- EPUB spec references in all error messages

### Fixed
- False positives: DOCTYPE entity detection, JavaScript detection
- Refined inline styles and large image warnings to reduce noise

## [1.2] - 2025-12-02

### Added
- Detection of large margin values that break PocketBook layout
- Enhanced critical summary to include margin layout issues
- Improved PocketBook compatibility checking

## [1.1] - 2025-12-01

### Fixed
- False positive detection of text-transform as CSS transform
- Reduced duplicate entity error reporting
- Improved accuracy of platform-specific issue detection

## [1.0] - 2025-11-30

### Added
- Initial release
- Multi-platform validation (PC readers, Apple Books, Kobo, PocketBook, InkBook, Kindle, Android)
- EPUB 2 & 3 support
- Structural validation (mimetype, container.xml, OPF package)
- Navigation validation (NCX for EPUB 2, nav document for EPUB 3)
- Content validation (XHTML/HTML, CSS, images, fonts)
- Detailed reports with line-by-line error reporting
