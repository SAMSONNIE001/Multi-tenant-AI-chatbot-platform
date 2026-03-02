from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"


class SimpleHtmlStackParser(HTMLParser):
    VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag not in self.VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.VOID_TAGS:
            return
        if not self.stack:
            self.errors.append(f"Unexpected closing tag </{tag}>")
            return
        last = self.stack[-1]
        if last != tag:
            self.errors.append(f"Mismatched closing tag </{tag}>; expected </{last}>")
            return
        self.stack.pop()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_html_structure(path: Path) -> list[str]:
    errors: list[str] = []
    text = read_text(path)
    parser = SimpleHtmlStackParser()
    parser.feed(text)
    parser.close()
    errors.extend(parser.errors)
    if parser.stack:
        errors.append(f"Unclosed tags: {', '.join(parser.stack[-5:])}")
    return [f"{path}: {e}" for e in errors]


def check_tenant_console_guardrails(path: Path) -> list[str]:
    errors: list[str] = []
    text = read_text(path)

    if 'id="apiBase" value="https://api.staunchbot.com"' in text:
        errors.append("apiBase must not default to production host.")

    sensitive_inputs = ("obAdminPassword", "lgEmail", "lgPassword")
    for input_id in sensitive_inputs:
        pattern = rf'id="{re.escape(input_id)}"[^>]*value="([^"]*)"'
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        if match.group(1).strip():
            errors.append(f'Input id="{input_id}" must default to an empty value.')

    banned_literals = (
        "StrongPass123!",
        "Abc12345!",
        "admin3@demo.com",
    )
    for literal in banned_literals:
        if literal in text:
            errors.append(f"Banned hardcoded credential/demo value found: {literal}")

    return [f"{path}: {e}" for e in errors]


def main() -> int:
    html_files = [
        FRONTEND_DIR / "dashboard.html",
        FRONTEND_DIR / "tenant-console.html",
        FRONTEND_DIR / "widget-test.html",
        FRONTEND_DIR / "embed-snippet.html",
    ]

    all_errors: list[str] = []
    for html_file in html_files:
        if not html_file.exists():
            all_errors.append(f"Missing required HTML file: {html_file}")
            continue
        all_errors.extend(check_html_structure(html_file))

    tenant_console = FRONTEND_DIR / "tenant-console.html"
    tenant_setup = FRONTEND_DIR / "tenant-setup.html"
    if tenant_console.exists():
        all_errors.extend(check_tenant_console_guardrails(tenant_console))
    if tenant_setup.exists():
        all_errors.extend(check_tenant_console_guardrails(tenant_setup))

    if all_errors:
        print("[FAIL] Frontend checks failed:")
        for error in all_errors:
            print(f"- {error}")
        return 1

    print("[OK] Frontend HTML sanity + tenant-console guardrails passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
