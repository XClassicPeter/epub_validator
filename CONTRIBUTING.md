# Contributing to EPUB Validator

Thank you for your interest in contributing to EPUB Validator! This document provides guidelines for contributing to the project.

## How to Contribute

### Reporting Bugs

If you find a bug, please create an issue with:

1. **Clear description** of the problem
2. **Steps to reproduce**
3. **Expected behavior** vs actual behavior
4. **EPUB file details** (if possible, provide a sample EPUB that demonstrates the issue)
5. **Platform information** (Python version, OS)

### Suggesting Features

Feature suggestions are welcome! Please:

1. Check existing issues to avoid duplicates
2. Provide clear use case for the feature
3. Explain how it improves EPUB validation
4. Reference EPUB specifications if applicable

### Contributing Code

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/your-feature-name`
3. **Make your changes** following the code style guidelines below
4. **Test your changes** with various EPUB files
5. **Commit with clear messages**: `git commit -m "Add feature: description"`
6. **Push to your fork**: `git push origin feature/your-feature-name`
7. **Submit a pull request**

## Code Style Guidelines

### Python Style

- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guide
- Use 4 spaces for indentation (no tabs)
- Maximum line length: 100 characters (docstrings/comments: 80)
- Use descriptive variable names
- Add type hints where appropriate

### Documentation

- All public methods must have docstrings
- Use triple quotes for docstrings: `"""Description"""`
- Include parameter descriptions and return types
- Add comments for complex logic

### Example

```python
def _validate_something(self, epub: zipfile.ZipFile, manifest: Dict) -> None:
    """Validate something in the EPUB.
    
    Args:
        epub: The opened EPUB file
        manifest: Dictionary of manifest items
    
    Returns:
        None. Issues are added to self.issues or self.warnings
    """
    # Implementation with clear comments
    pass
```

## Testing

### Before Submitting

1. Test with valid EPUB 2 and EPUB 3 files (no false positives)
2. Test with EPUBs containing the issue your code detects
3. Ensure error messages include:
   - File path and line number (where applicable)
   - Clear description of the problem
   - How to fix it
   - EPUB specification reference

### Test Files

When adding new validation, ideally provide:
- A minimal EPUB demonstrating the issue
- Description of what should be detected
- Expected error message

## Adding New Validations

When adding new validation checks:

1. **Research the specification**: Link to relevant EPUB spec section
2. **Identify the issue**: What breaks, which readers are affected
3. **Implement detection**: Add method following naming convention `_validate_xxx` or `_check_xxx`
4. **Categorize correctly**: 
   - `self.issues['platform']` for errors
   - `self.warnings['platform']` for warnings
   - Choose correct platform: general, pc_reader, apple_books, kindle, kobo, pocketbook, inkbook, android
5. **Add specification reference**: Update EXPLANATIONS dictionary
6. **Test thoroughly**: Both positive and negative cases

### Example: Adding New Check

```python
def _validate_new_feature(self, epub: zipfile.ZipFile, manifest: Dict):
    """Validate new feature according to EPUB 3.3 § X.Y"""
    for item_id, item_info in manifest.items():
        if item_info['media_type'] == 'relevant/type':
            try:
                content = epub.read(item_info['href']).decode('utf-8', errors='ignore')
                
                if 'problematic-pattern' in content:
                    self.issues['general'].append(
                        f"{item_info['href']}: Problem detected - "
                        f"how to fix it (EPUB 3.3 § X.Y)"
                    )
            except Exception as e:
                # Handle gracefully, don't crash
                pass
```

Then add to EXPLANATIONS:

```python
EXPLANATIONS = {
    # ... existing entries ...
    r"Problem detected": "Reference: Explanation with spec link. EPUB 3.3 § X.Y",
}
```

## Specification References

Always reference the EPUB specification when adding validations:

- **EPUB 3.3**: [https://www.w3.org/TR/epub-33/](https://www.w3.org/TR/epub-33/)
- **EPUB 3.2**: [https://www.w3.org/TR/epub-32/](https://www.w3.org/TR/epub-32/)
- **EPUB 2.0.1**: [http://idpf.org/epub/201](http://idpf.org/epub/201)
- **EPUB Accessibility**: [https://www.w3.org/TR/epub-a11y-11/](https://www.w3.org/TR/epub-a11y-11/)
- **OCF 3.0**: [https://www.w3.org/TR/epub-33/#sec-ocf](https://www.w3.org/TR/epub-33/#sec-ocf)

## Platform-Specific Validations

When adding platform-specific checks:

1. **Verify the limitation**: Test on actual device/software
2. **Document the behavior**: What happens when the issue is present
3. **Provide workaround**: How to fix or avoid the issue
4. **Test on other platforms**: Ensure fix doesn't break elsewhere

### Supported Platforms

- `pc_reader`: Calibre, Adobe Digital Editions, desktop readers
- `apple_books`: iOS/macOS Books app
- `kindle`: Amazon Kindle (requires MOBI conversion)
- `kobo`: Kobo e-readers and apps
- `pocketbook`: PocketBook e-readers
- `inkbook`: InkBook e-readers
- `android`: Android reader apps (various)
- `general`: Issues affecting multiple/all platforms

## Reducing False Positives

False positives erode trust in the tool. When implementing checks:

1. **Be precise**: Use specific patterns, not broad matches
2. **Handle edge cases**: Comments, escaped text, quoted examples
3. **Test extensively**: Try to break your detection
4. **Use regex carefully**: Test regex patterns thoroughly
5. **Consider context**: Same pattern may be valid in one context, invalid in another

### Example: Avoiding False Positives

```python
# BAD - Too broad, matches comments
if '<script' in content:
    self.warnings['general'].append("JavaScript found")

# GOOD - Remove comments first, use precise regex
content_no_comments = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
if re.search(r'<script[>\s]', content_no_comments, re.IGNORECASE):
    self.warnings['general'].append("JavaScript found")
```

## Error Message Guidelines

Good error messages are:

1. **Specific**: Include file path, line number if possible
2. **Actionable**: Tell user how to fix it
3. **Referenced**: Link to specification
4. **Clear**: Use simple language

### Template

```
{file_path} (line {line_num}): {problem_description} - {how_to_fix} ({spec_reference})
```

### Examples

```
# Good
"chapter1.xhtml (line 45): Undeclared entity 'nbsp' - Replace &nbsp; with &#160; (EPUB 3.3 § 2.3)"

# Bad
"Entity error in file"
```

## Commit Messages

Use clear, descriptive commit messages:

```
# Good
"Add validation for duplicate IDs across documents"
"Fix false positive in CSS transform detection"
"Update README with PocketBook rendering differences"

# Bad
"fix bug"
"update"
```

## Pull Request Process

1. Ensure all tests pass (if you add tests)
2. Update README.md if adding user-facing features
3. Update CHANGELOG in docstring if significant change
4. Describe your changes clearly in the PR
5. Link related issues
6. Be responsive to feedback

## Code of Conduct

- Be respectful and constructive
- Welcome newcomers and help them contribute
- Focus on what's best for the project
- Accept constructive criticism gracefully

## Questions?

Feel free to:
- Open an issue for discussion
- Ask questions in pull requests
- Reach out to maintainers

---

Thank you for contributing to EPUB Validator! Your efforts help improve e-book quality for readers everywhere.
