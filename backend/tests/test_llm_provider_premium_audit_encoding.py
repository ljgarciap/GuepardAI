"""
test_llm_provider_premium_audit_encoding.py — regression for a real crash found
while generating decks for the Synthesis Studio v2 elicitation (2026-09-18).

log_premium_audit() opened its log file without an explicit encoding — the same
bug already found and fixed once in log_audit() (see
docs/ai/contracts/default-llm-template-merge-outline-adr.md), left unfixed in
its sibling function. On a host whose default codepage doesn't cover a
character in the LLM's response (e.g. "≠" on Windows cp1252), the write itself
raised UnicodeEncodeError and took down the entire premium generation
pipeline — not just the audit log.
"""
import os

import pytest

from providers.llm_provider import log_premium_audit


@pytest.mark.unit
class TestLogPremiumAuditEncoding:

    def test_writes_non_ascii_content_without_raising(self, tmp_path, monkeypatch):
        log_file = tmp_path / "premium_llm_audit.log"
        monkeypatch.setattr(
            "providers.llm_provider.__file__",
            str(tmp_path / "llm_provider.py"),
        )
        # log_premium_audit derives its path from __file__'s directory.
        log_premium_audit("DESIGN_JSON", "Aspect ratio ≠ target — reasoning with a → arrow and an em—dash.")

        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "≠" in content
        assert "DESIGN_JSON" in content
