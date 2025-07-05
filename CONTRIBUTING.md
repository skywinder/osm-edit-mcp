# Contributing to OSM Edit MCP Server

Thank you for your interest in contributing to OSM Edit MCP Server! This document provides guidelines and instructions for contributing to the project.

## 🤝 Code of Conduct

By participating in this project, you agree to abide by our code of conduct:
- Be respectful and inclusive
- Welcome newcomers and help them get started
- Focus on constructive criticism
- Respect differing viewpoints and experiences

## 🚀 Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/osm-edit-mcp.git
   cd osm-edit-mcp
   ```

### Option 1: Using uv (Recommended)
```bash
# Install dependencies
uv sync

# Install with dev dependencies
uv sync --all-extras
```

### Option 2: Using pip
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -e .[dev]
```

## 🔧 Development Setup

### Environment Configuration

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
2. Configure for development (keep `OSM_USE_DEV_API=true`)
3. Set up OAuth credentials following the README instructions

### Running Tests

#### With uv
```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/osm_edit_mcp

# Run specific test file
uv run pytest tests/test_config.py

# Run integration tests
uv run python test_comprehensive.py
```

#### With pip/python
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/osm_edit_mcp

# Run specific test file
pytest tests/test_config.py

# Run integration tests
python test_comprehensive.py
```

### Code Quality Tools

```bash
# Format code with black
black src/ tests/

# Sort imports
isort src/ tests/

# Type checking
mypy src/osm_edit_mcp

# Linting
flake8 src/ tests/

# Security checks
bandit -r src/
```

## 📝 Making Changes

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation updates
- `refactor/description` - Code refactoring
- `test/description` - Test improvements

### Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
type(scope): description

[optional body]

[optional footer(s)]
```

Examples:
- `feat(tools): add bulk node update functionality`
- `fix(auth): handle expired OAuth tokens`
- `docs(readme): update installation instructions`
- `test(config): add unit tests for configuration`

## 🧪 Testing Guidelines

### Writing Tests

1. **Unit Tests**: Test individual functions and classes
   - Place in `tests/test_*.py`
   - Use pytest fixtures for common setup
   - Mock external API calls

2. **Integration Tests**: Test complete workflows
   - Use the development OSM API
   - Clean up test data after tests

3. **Test Coverage**: Aim for >80% coverage
   - Critical paths should have 100% coverage
   - Document why certain code is excluded

### Example Test

```python
import pytest
from src.osm_edit_mcp.server import validate_coordinates

def test_validate_coordinates_valid():
    """Test validation of valid coordinates."""
    result = await validate_coordinates(51.5074, -0.1278)
    assert result["success"] is True
    assert "location" in result["data"]
```

## 📦 Submitting Changes

1. **Ensure all tests pass**:
   ```bash
   pytest
   mypy src/osm_edit_mcp
   flake8 src/ tests/
   ```

2. **Update documentation** if needed:
   - Update README.md for new features
   - Add docstrings to new functions
   - Update CHANGELOG.md

3. **Create a Pull Request**:
   - Use a clear, descriptive title
   - Reference any related issues
   - Include a description of changes
   - Add screenshots for UI changes

### Pull Request Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Tests added/updated
```

## 🏗️ Architecture Guidelines

### Adding New Tools

1. Define the tool in `server.py` using the `@mcp.tool()` decorator
2. Include comprehensive docstrings
3. Validate all inputs
4. Return consistent response format:
   ```python
   {
       "success": bool,
       "data": dict,  # On success
       "error": str,  # On failure
       "message": str
   }
   ```
5. Add corresponding tests
6. Update documentation

### Error Handling

- Use try-except blocks for all external calls
- Log errors appropriately
- Return user-friendly error messages
- Never expose sensitive information

## 📚 Documentation

### Docstring Format

Use Google-style docstrings:

```python
def get_osm_node(node_id: int) -> Dict[str, Any]:
    """Get an OSM node by ID.
    
    Args:
        node_id: The ID of the node to retrieve
        
    Returns:
        Dictionary containing node data including coordinates and tags
        
    Raises:
        HTTPError: If the API request fails
    """
```

### README Updates

When adding features, update:
- Feature list
- Tool documentation
- Usage examples
- Configuration options

## 🐛 Reporting Issues

### Bug Reports

Include:
- OSM Edit MCP Server version
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Error messages/logs

### Feature Requests

Include:
- Use case description
- Proposed implementation
- API design suggestions
- Potential impacts

## 💬 Getting Help

- **GitHub Issues**: For bugs and features
- **Discussions**: For questions and ideas
- **Stack Overflow**: Tag with `osm-edit-mcp`

## 🎉 Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Given credit in commit messages

Thank you for contributing to OSM Edit MCP Server!