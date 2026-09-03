#!/usr/bin/env python3
"""
Security Audit Script for OSM Edit MCP Server

This script performs security checks on the codebase and configuration.
"""

import ast
import fnmatch
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 only
    import tomli as tomllib


class SecurityAuditor:
    """Perform security audit on OSM Edit MCP Server."""

    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.issues: List[Dict[str, Any]] = []

    def add_issue(
        self,
        severity: str,
        category: str,
        description: str,
        file_path: str = None,
        line: int = None,
    ):
        """Add a security issue."""
        self.issues.append(
            {
                "severity": severity,
                "category": category,
                "description": description,
                "file_path": file_path,
                "line": line,
            }
        )

    def check_sensitive_files(self):
        """Check for sensitive files that shouldn't be committed."""
        print("🔍 Checking for sensitive files...")

        sensitive_patterns = [
            ".env",
            ".claude/settings.local.json",
            "*.key",
            "*.pem",
            "*.p12",
            ".osm_token_*.json",
            "oauth_tokens.json",
        ]

        gitignore_path = self.root_path / ".gitignore"
        if gitignore_path.exists():
            with open(gitignore_path, "r") as f:
                gitignore_content = f.read()

            for pattern in sensitive_patterns:
                if pattern not in gitignore_content:
                    self.add_issue(
                        "HIGH",
                        "Configuration",
                        f"Pattern '{pattern}' not found in .gitignore",
                        str(gitignore_path),
                    )
        else:
            self.add_issue("CRITICAL", "Configuration", ".gitignore file not found")

        try:
            tracked_output = subprocess.run(
                ["git", "-C", str(self.root_path), "ls-files", "-z"],
                check=True,
                capture_output=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            self.add_issue(
                "HIGH",
                "Configuration",
                f"Unable to inspect tracked files: {type(exc).__name__}",
                str(self.root_path),
            )
            return

        tracked_files = [
            entry.decode("utf-8", errors="replace")
            for entry in tracked_output.split(b"\0")
            if entry
        ]
        tracked_sensitive = sorted(
            file_path
            for file_path in tracked_files
            if any(
                file_path == pattern
                or fnmatch.fnmatch(file_path, pattern)
                or fnmatch.fnmatch(Path(file_path).name, pattern)
                for pattern in sensitive_patterns
            )
        )
        for file_path in tracked_sensitive:
            self.add_issue(
                "CRITICAL",
                "Configuration",
                "Sensitive file is tracked by Git; .gitignore is not sufficient",
                file_path,
            )

    def check_oauth_security(self):
        """Check OAuth implementation security."""
        print("🔐 Checking OAuth security...")

        oauth_file = self.root_path / "oauth_auth.py"
        if oauth_file.exists():
            with open(oauth_file, "r") as f:
                content = f.read()

            # Check for hardcoded credentials
            if re.search(r'client_secret\s*=\s*["\'][^"\']+["\']', content):
                self.add_issue(
                    "CRITICAL",
                    "Authentication",
                    "Potential hardcoded client secret found",
                    str(oauth_file),
                )

            # Check for keyring usage
            if "keyring" not in content:
                self.add_issue(
                    "HIGH",
                    "Authentication",
                    "OAuth tokens should be stored using keyring",
                    str(oauth_file),
                )

    def check_api_security(self):
        """Check API security practices."""
        print("🌐 Checking API security...")

        package_path = self.root_path / "src" / "osm_edit_mcp"
        server_files = sorted(package_path.glob("*.py"))
        if server_files:
            content = "\n".join(
                path.read_text(encoding="utf-8") for path in server_files
            )

            # Check for HTTPS usage
            if "http://" in content and "https://" not in content:
                self.add_issue(
                    "HIGH",
                    "Network",
                    "Using HTTP instead of HTTPS for API calls",
                    str(package_path),
                )

            # Check for rate limiting
            if "rate_limit" not in content.lower():
                self.add_issue(
                    "MEDIUM",
                    "API",
                    "No rate limiting implementation found",
                    str(package_path),
                )

            # Check for input validation
            if not re.search(r"def\s+validate_\w+", content):
                self.add_issue(
                    "MEDIUM",
                    "Validation",
                    "Limited input validation functions found",
                    str(package_path),
                )

    def check_dependencies(self):
        """Check that direct dependencies in pyproject.toml are constrained."""
        print("📦 Checking dependencies...")

        # This is a declaration check; use pip-audit for vulnerability data.
        pyproject_file = self.root_path / "pyproject.toml"
        if not pyproject_file.exists():
            self.add_issue(
                "HIGH",
                "Dependencies",
                "pyproject.toml not found",
                str(pyproject_file),
            )
            return

        try:
            with pyproject_file.open("rb") as file_handle:
                project = tomllib.load(file_handle).get("project", {})
        except (OSError, tomllib.TOMLDecodeError) as exc:
            self.add_issue(
                "HIGH",
                "Dependencies",
                f"Unable to read dependency metadata: {exc}",
                str(pyproject_file),
            )
            return

        dependencies = list(project.get("dependencies", []))
        for group_dependencies in project.get("optional-dependencies", {}).values():
            dependencies.extend(group_dependencies)

        if not dependencies:
            self.add_issue(
                "MEDIUM",
                "Dependencies",
                "No project dependencies declared in pyproject.toml",
                str(pyproject_file),
            )
            return

        unconstrained = [
            dependency
            for dependency in dependencies
            if not re.search(r"(?:===|==|~=|!=|<=|>=|<|>)", dependency)
        ]
        if unconstrained:
            self.add_issue(
                "MEDIUM",
                "Dependencies",
                "Direct dependencies without version constraints: "
                + ", ".join(unconstrained),
                str(pyproject_file),
            )

    def check_logging_security(self):
        """Flag direct logging of secret-bearing values, not harmless wording."""
        print("📝 Checking logging security...")

        sensitive_names = {
            "access_token",
            "api_key",
            "authorization",
            "refresh_token",
            "client_secret",
            "password",
            "secret",
            "token",
        }
        logging_methods = {"debug", "info", "warning", "error", "exception"}

        def sensitive_name(value: str) -> bool:
            lowered = value.casefold()
            return (
                lowered in sensitive_names
                or lowered.endswith("_api_key")
                or lowered.endswith("_authorization")
                or lowered.endswith("_password")
                or lowered.endswith("_secret")
                or lowered.endswith("_token")
            )

        def exposes_sensitive_value(argument: ast.AST) -> bool:
            if isinstance(argument, ast.Name) and argument.id == "token_data":
                return True
            for child in ast.walk(argument):
                if isinstance(child, ast.Name) and sensitive_name(child.id):
                    return True
                if isinstance(child, ast.Attribute) and sensitive_name(child.attr):
                    return True
                if isinstance(child, ast.Subscript):
                    key = child.slice
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        if sensitive_name(key.value):
                            return True
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "get"
                    and child.args
                    and isinstance(child.args[0], ast.Constant)
                    and isinstance(child.args[0].value, str)
                    and sensitive_name(child.args[0].value)
                ):
                    return True
            return False

        for py_file in self.root_path.rglob("*.py"):
            relative_path = py_file.relative_to(self.root_path)
            if (
                relative_path.name.startswith("test_")
                or "tests" in relative_path.parts
                or ".venv" in relative_path.parts
                or "venv" in relative_path.parts
            ):
                continue

            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except (OSError, SyntaxError) as exc:
                self.add_issue(
                    "HIGH",
                    "Logging",
                    f"Unable to inspect Python source: {type(exc).__name__}",
                    str(py_file),
                )
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                is_print = isinstance(node.func, ast.Name) and node.func.id == "print"
                is_logger = (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr in logging_methods
                )
                if not (is_print or is_logger):
                    continue
                arguments = [*node.args, *(item.value for item in node.keywords)]
                if any(exposes_sensitive_value(argument) for argument in arguments):
                    self.add_issue(
                        "HIGH",
                        "Logging",
                        "Potential direct logging of a secret-bearing value",
                        str(py_file),
                        node.lineno,
                    )
                    break

    def generate_report(self):
        """Generate security audit report."""
        print("\n" + "=" * 60)
        print("SECURITY AUDIT REPORT")
        print("=" * 60)

        if not self.issues:
            print("✅ No security issues found!")
            return

        # Group by severity
        by_severity = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": []}

        for issue in self.issues:
            by_severity[issue["severity"]].append(issue)

        # Print issues by severity
        for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            issues = by_severity[severity]
            if issues:
                print(f"\n{severity} Issues ({len(issues)}):")
                print("-" * 40)
                for issue in issues:
                    print(f"• [{issue['category']}] {issue['description']}")
                    if issue.get("file_path"):
                        print(f"  File: {issue['file_path']}")
                    if issue.get("line"):
                        print(f"  Line: {issue['line']}")

        # Summary
        print(f"\nTotal Issues: {len(self.issues)}")
        print(f"Critical: {len(by_severity['CRITICAL'])}")
        print(f"High: {len(by_severity['HIGH'])}")
        print(f"Medium: {len(by_severity['MEDIUM'])}")
        print(f"Low: {len(by_severity['LOW'])}")

        # Save to file
        report_path = self.root_path / "security_audit_report.json"
        from datetime import datetime

        with open(report_path, "w") as f:
            json.dump(
                {
                    "timestamp": datetime.now().isoformat(),
                    "total_issues": len(self.issues),
                    "by_severity": {k: len(v) for k, v in by_severity.items()},
                    "issues": self.issues,
                },
                f,
                indent=2,
            )

        print(f"\nDetailed report saved to: {report_path}")

    def run_audit(self) -> bool:
        """Run all security checks."""
        print("🔒 Starting Security Audit for OSM Edit MCP Server")
        print("=" * 60)

        self.check_sensitive_files()
        self.check_oauth_security()
        self.check_api_security()
        self.check_dependencies()
        self.check_logging_security()

        self.generate_report()
        return not any(
            issue["severity"] in {"CRITICAL", "HIGH"} for issue in self.issues
        )


def main():
    """Main entry point."""
    root_path = Path(__file__).parent.parent
    auditor = SecurityAuditor(root_path)
    if not auditor.run_audit():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
