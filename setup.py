#!/usr/bin/env python
"""Setup script for OSM Edit MCP Server."""

from setuptools import setup, find_packages

# Read long description from README
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="osm-edit-mcp",
    version="0.1.0",
    author="pk",
    author_email="right.crew7885@fastmail.com",
    description="Model Context Protocol server for editing OpenStreetMap data",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/skywinder/osm-edit-mcp",
    project_urls={
        "Bug Tracker": "https://github.com/skywinder/osm-edit-mcp/issues",
        "Documentation": "https://github.com/skywinder/osm-edit-mcp/blob/main/README.md",
        "Source Code": "https://github.com/skywinder/osm-edit-mcp",
    },
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: GIS",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",
    install_requires=[
        "mcp>=1.10.0",
        "httpx>=0.25.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "python-dotenv>=1.0.0",
        "authlib>=1.2.0",
        "keyring>=24.0.0",
        "anyio>=3.0.0",
        "structlog>=23.0.0",
        "requests>=2.31.0",
        "aiofiles>=23.0.0",
        "aiohttp>=3.12.13",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "isort>=5.0.0",
            "mypy>=1.0.0",
            "flake8>=6.0.0",
            "pre-commit>=3.0.0",
            "bandit>=1.7.0",
            "safety>=2.3.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "osm-edit-mcp=osm_edit_mcp.server:main",
        ],
    },
)