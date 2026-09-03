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

### Install the locked development environment

```bash
# Install the dependencies declared by pyproject.toml exactly as locked
uv sync --locked --extra dev
```

## 🔧 Development Setup

### Environment Configuration

1. Copy the example environment file:
   ```bash
   install -m 600 .env.example .env
   export OSM_EDIT_MCP_ENV_FILE="$PWD/.env"
   ```
2. Configure for development (keep `OSM_USE_DEV_API=true`)
3. Set up OAuth credentials following the README instructions

### Running Tests

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

### Code Quality Tools

```bash
# Format code with black
uv run black src/ tests/

# Sort imports
uv run isort src/ tests/

# Type checking
uv run mypy src/osm_edit_mcp

# Linting
uv run flake8 src/ tests/

# Security checks
uv run bandit -r src/
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

3. **Test Coverage**: Keep the repository gate at or above 60%
   - Add focused tests for changed safety-critical paths
   - Document why an important branch cannot be exercised

### Example Test

```python
import pytest

from osm_edit_mcp.server import validate_coordinates


@pytest.mark.asyncio
async def test_validate_coordinates_rejects_invalid_latitude():
    """Invalid coordinates are rejected locally without a network lookup."""
    result = await validate_coordinates(91.0, 0.0)
    assert result["success"] is True
    assert result["data"]["is_valid"] is False
```

## 📦 Submitting Changes

1. **Ensure all tests pass**:
   ```bash
   uv sync --locked --extra dev
   uv run pytest
   uv run mypy src/osm_edit_mcp
   uv run flake8 src/ tests/
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

1. Define read-only and validation tools in `read_tools.py`, or mutation
   workflows in `write_tools.py`, using the shared `@mcp.tool()` decorator
   from `app.py`
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

`server.py` is a compatibility facade and entry point. Keep implementation
logic in the focused modules:

- `config.py`: environment-backed configuration and logging
- `token_store.py`: OAuth token persistence and identity metadata
- `http_client.py`: authenticated/public HTTP client factories
- `xml_models.py`: OSM XML serialization and parsing
- `natural_language.py`: pure parsing and tag mappings
- `read_tools.py`: read-only, discovery, export, and validation tools
- `write_tools.py`: changesets, mutations, and higher-level write workflows

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
