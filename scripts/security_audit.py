#!/usr/bin/env python3
"""
Security Audit Script for OSM Edit MCP Server

This script performs security checks on the codebase and configuration.
"""

import os
import sys
import json
import re
from pathlib import Path
from typing import List, Dict, Any


class SecurityAuditor:
    """Perform security audit on OSM Edit MCP Server."""
    
    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.issues: List[Dict[str, Any]] = []
        
    def add_issue(self, severity: str, category: str, description: str, file_path: str = None, line: int = None):
        """Add a security issue."""
        self.issues.append({
            "severity": severity,
            "category": category,
            "description": description,
            "file_path": file_path,
            "line": line
        })
    
    def check_sensitive_files(self):
        """Check for sensitive files that shouldn't be committed."""
        print("🔍 Checking for sensitive files...")
        
        sensitive_patterns = [
            ".env",
            "*.key",
            "*.pem",
            "*.p12",
            ".osm_token_*.json",
            "oauth_tokens.json"
        ]
        
        gitignore_path = self.root_path / ".gitignore"
        if gitignore_path.exists():
            with open(gitignore_path, 'r') as f:
                gitignore_content = f.read()
            
            for pattern in sensitive_patterns:
                if pattern not in gitignore_content:
                    self.add_issue(
                        "HIGH",
                        "Configuration",
                        f"Pattern '{pattern}' not found in .gitignore",
                        str(gitignore_path)
                    )
        else:
            self.add_issue(
                "CRITICAL",
                "Configuration",
                ".gitignore file not found"
            )
    
    def check_oauth_security(self):
        """Check OAuth implementation security."""
        print("🔐 Checking OAuth security...")
        
        oauth_file = self.root_path / "oauth_auth.py"
        if oauth_file.exists():
            with open(oauth_file, 'r') as f:
                content = f.read()
            
            # Check for hardcoded credentials
            if re.search(r'client_secret\s*=\s*["\'][^"\']+["\']', content):
                self.add_issue(
                    "CRITICAL",
                    "Authentication",
                    "Potential hardcoded client secret found",
                    str(oauth_file)
                )
            
            # Check for keyring usage
            if "keyring" not in content:
                self.add_issue(
                    "HIGH",
                    "Authentication",
                    "OAuth tokens should be stored using keyring",
                    str(oauth_file)
                )
    
    def check_api_security(self):
        """Check API security practices."""
        print("🌐 Checking API security...")
        
        server_file = self.root_path / "src" / "osm_edit_mcp" / "server.py"
        if server_file.exists():
            with open(server_file, 'r') as f:
                content = f.read()
            
            # Check for HTTPS usage
            if "http://" in content and "https://" not in content:
                self.add_issue(
                    "HIGH",
                    "Network",
                    "Using HTTP instead of HTTPS for API calls",
                    str(server_file)
                )
            
            # Check for rate limiting
            if "rate_limit" not in content.lower():
                self.add_issue(
                    "MEDIUM",
                    "API",
                    "No rate limiting implementation found",
                    str(server_file)
                )
            
            # Check for input validation
            if not re.search(r'def\s+validate_\w+', content):
                self.add_issue(
                    "MEDIUM",
                    "Validation",
                    "Limited input validation functions found",
                    str(server_file)
                )
    
    def check_dependencies(self):
        """Check for known vulnerable dependencies."""
        print("📦 Checking dependencies...")
        
        # This is a simplified check - in production, use tools like safety or pip-audit
        requirements_file = self.root_path / "requirements.txt"
        if requirements_file.exists():
            with open(requirements_file, 'r') as f:
                deps = f.read()
            
            # Check for minimum versions
            if not re.search(r'>=|~=|==', deps):
                self.add_issue(
                    "MEDIUM",
                    "Dependencies",
                    "No version constraints found in requirements.txt",
                    str(requirements_file)
                )
    
    def check_logging_security(self):
        """Check for secure logging practices."""
        print("📝 Checking logging security...")
        
        for py_file in self.root_path.rglob("*.py"):
            if "test" in str(py_file):
                continue
                
            with open(py_file, 'r') as f:
                content = f.read()
            
            # Check for logging of sensitive data
            sensitive_log_patterns = [
                r'logger\.\w+\([^)]*password[^)]*\)',
                r'logger\.\w+\([^)]*secret[^)]*\)',
                r'logger\.\w+\([^)]*token[^)]*\)',
                r'print\([^)]*password[^)]*\)',
                r'print\([^)]*secret[^)]*\)',
                r'print\([^)]*token[^)]*\)'
            ]
            
            for pattern in sensitive_log_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    self.add_issue(
                        "HIGH",
                        "Logging",
                        "Potential logging of sensitive data",
                        str(py_file)
                    )
    
    def generate_report(self):
        """Generate security audit report."""
        print("\n" + "=" * 60)
        print("SECURITY AUDIT REPORT")
        print("=" * 60)
        
        if not self.issues:
            print("✅ No security issues found!")
            return
        
        # Group by severity
        by_severity = {
            "CRITICAL": [],
            "HIGH": [],
            "MEDIUM": [],
            "LOW": []
        }
        
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
                    if issue.get('file_path'):
                        print(f"  File: {issue['file_path']}")
                    if issue.get('line'):
                        print(f"  Line: {issue['line']}")
        
        # Summary
        print(f"\nTotal Issues: {len(self.issues)}")
        print(f"Critical: {len(by_severity['CRITICAL'])}")
        print(f"High: {len(by_severity['HIGH'])}")
        print(f"Medium: {len(by_severity['MEDIUM'])}")
        print(f"Low: {len(by_severity['LOW'])}")
        
        # Save to file
        report_path = self.root_path / "security_audit_report.json"
        with open(report_path, 'w') as f:
            json.dump({
                "timestamp": str(Path.ctime(Path.cwd())),
                "total_issues": len(self.issues),
                "by_severity": {k: len(v) for k, v in by_severity.items()},
                "issues": self.issues
            }, f, indent=2)
        
        print(f"\nDetailed report saved to: {report_path}")
    
    def run_audit(self):
        """Run all security checks."""
        print("🔒 Starting Security Audit for OSM Edit MCP Server")
        print("=" * 60)
        
        self.check_sensitive_files()
        self.check_oauth_security()
        self.check_api_security()
        self.check_dependencies()
        self.check_logging_security()
        
        self.generate_report()


def main():
    """Main entry point."""
    root_path = Path(__file__).parent.parent
    auditor = SecurityAuditor(root_path)
    auditor.run_audit()


if __name__ == "__main__":
    main()