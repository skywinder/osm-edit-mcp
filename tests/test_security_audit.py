"""Regression tests for the repository security audit."""

from scripts.security_audit import SecurityAuditor


def test_logging_audit_detects_prefixed_secret_names(tmp_path):
    """Common provider-prefixed secret variables must not bypass the AST scan."""
    (tmp_path / "api_key_leak.py").write_text(
        "logger.info(openai_api_key)\n", encoding="utf-8"
    )
    (tmp_path / "authorization_leak.py").write_text(
        "print(proxy_authorization)\n", encoding="utf-8"
    )

    auditor = SecurityAuditor(tmp_path)
    auditor.check_logging_security()

    assert len(auditor.issues) == 2
    assert {issue["severity"] for issue in auditor.issues} == {"HIGH"}


def test_logging_audit_ignores_harmless_security_wording(tmp_path):
    """Security prose in a literal is not evidence that a secret is exposed."""
    (tmp_path / "safe_log.py").write_text(
        'logger.info("OAuth token storage is enabled")\n', encoding="utf-8"
    )

    auditor = SecurityAuditor(tmp_path)
    auditor.check_logging_security()

    assert auditor.issues == []
