"""Setup script for Token Listing FDV and Allocation Benchmark Tool."""

from setuptools import setup, find_packages
from pathlib import Path

# Read version
version = "0.1.0"

# Read README for long description
readme_path = Path(__file__).parent / "README.md"
long_description = ""
if readme_path.exists():
    long_description = readme_path.read_text(encoding="utf-8")

setup(
    name="token-listing-tool",
    version=version,
    description="Token Listing FDV and Allocation Benchmark Tool for crypto tokenomics analysis",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Tokenomics Team",
    python_requires=">=3.10",
    packages=find_packages(exclude=["tests", "tests.*", "examples"]),
    package_data={
        "": ["*.yaml", "*.yml", "*.json"],
    },
    include_package_data=True,
    install_requires=[
        "pydantic>=2.0.0",
        "httpx>=0.24.0",
        "pyyaml>=6.0",
        "ccxt>=4.0.0",
        "typer>=0.9.0",
        "rich>=13.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "ruff>=0.0.280",
            "mypy>=1.4.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "token-listing=cli.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Financial and Insurance Industry",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
)
