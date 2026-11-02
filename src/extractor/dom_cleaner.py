"""HTML DOM cleaner: strips scripts/SVGs/nav/footers, surfaces hidden modal/accordion text, and converts to Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from bs4 import BeautifulSoup, Comment, NavigableString, Tag


@dataclass
class CleanedDOMArtifact:
    """Result of cleaning raw HTML into structured Markdown and persisting the .md audit snapshot."""

    markdown_text: str
    markdown_path: Optional[Path]
    char_count: int
    surfaced_modals_count: int


class DOMCleaner:
    """
    Deterministic HTML-to-Markdown cleaner optimized for LATAM telecom plan catalogs.

    1. Surfaces hidden modal, tooltip, and legal terms blocks (`modal`, `tyc`, `terms`, `accordion`, `collapse`)
       before stripping layout chrome so promo durations and VAS post-promo prices are never lost.
    2. Preserves verbatim `alt` and `aria-label` text on `<img>` tags (critical when OTT providers like
       Netflix, Max, Disney+, or Win Sports+ appear as brand logos inside plan cards).
    3. Removes `<script>`, `<style>`, `<svg>`, `<noscript>`, `<iframe>`, `<canvas>`, top-level `<nav>`,
       and `<footer>` chrome.
    4. Emits clean, structured Markdown and writes the `.md` audit snapshot to disk.
    """

    STRIP_TAGS = {
        "script",
        "style",
        "svg",
        "noscript",
        "iframe",
        "canvas",
        "video",
        "audio",
        "source",
        "track",
        "map",
        "object",
        "embed",
        "link",
        "meta",
    }

    NOISE_SELECTORS = [
        "nav",
        "footer",
        "[role='navigation']",
        "[role='contentinfo']",
        "#onetrust-consent-sdk",
        "#CybotCookiebotDialog",
        "[class*='cookie-banner' i]",
        "[class*='cookie-consent' i]",
        "[class*='chat-widget' i]",
        "[id*='whatsapp-button' i]",
    ]

    HIDDEN_TERMS_SELECTORS = [
        "[class*='modal' i]",
        "[class*='tyc' i]",
        "[class*='terminos' i]",
        "[class*='condiciones' i]",
        "[class*='legal' i]",
        "[class*='accordion-collapse' i]",
        "[class*='accordion-content' i]",
        "[class*='tooltip-content' i]",
        "[aria-hidden='true']",
    ]

    TERMS_KEYWORDS_RE = re.compile(
        r"(meses|tarifa|precio|iva|impuesto|mbps|megas|fibra|netflix|disney|max|prime|"
        r"paramount|vix|universal|spotify|tigo sports|win sports|tnt sports|flow|promoci[óo]n|vigencia|estrato)",
        re.IGNORECASE,
    )

    def clean_html_to_markdown(
        self,
        raw_html: str,
        output_md_path: Optional[Path] = None,
        metadata_header: Optional[dict] = None,
    ) -> CleanedDOMArtifact:
        """Clean raw HTML into structured Markdown and optionally persist the audit `.md` file."""
        try:
            soup = BeautifulSoup(raw_html or "", "lxml")
        except Exception:
            soup = BeautifulSoup(raw_html or "", "html.parser")

        # 1. Remove HTML comments and non-content tags
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        for tag_name in self.STRIP_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # 2. Extract and preserve hidden modal / legal terms blocks before removing page chrome
        surfaced_blocks: List[str] = []
        seen_modal_texts: set[str] = set()
        for selector in self.HIDDEN_TERMS_SELECTORS:
            for node in soup.select(selector):
                if not isinstance(node, Tag):
                    continue
                is_hidden = (
                    node.get("aria-hidden") == "true"
                    or "hidden" in (node.get("class") or [])
                    or "modal" in " ".join(node.get("class") or []).lower()
                    or "display:none" in str(node.get("style", "")).replace(" ", "").lower()
                )
                if not is_hidden:
                    continue
                txt = self._normalize_inline_whitespace(node.get_text(" ", strip=True))
                if len(txt) >= 25 and self.TERMS_KEYWORDS_RE.search(txt):
                    if txt not in seen_modal_texts:
                        seen_modal_texts.add(txt)
                        surfaced_blocks.append(txt)

        # 3. Strip navigation, footers, cookie banners, and top site header (keep headers inside plan cards)
        for selector in self.NOISE_SELECTORS:
            for node in soup.select(selector):
                node.decompose()

        for header_tag in soup.find_all("header"):
            parent_names = {p.name for p in header_tag.parents if isinstance(p, Tag)}
            parent_classes = " ".join(
                " ".join(p.get("class") or [])
                for p in header_tag.parents
                if isinstance(p, Tag)
            ).lower()
            is_inside_card = (
                "article" in parent_names
                or "section" in parent_names
                or any(k in parent_classes for k in ("card", "plan", "offer", "paquete", "tariff"))
            )
            if not is_inside_card:
                header_tag.decompose()

        # 4. Replace <img> tags that carry meaningful verbatim alt/aria-label attributes with explicit text markers
        for img in soup.find_all("img"):
            alt_text = (img.get("alt") or img.get("aria-label") or img.get("title") or "").strip()
            if alt_text and len(alt_text) <= 120:
                img.replace_with(NavigableString(f" [IMG_ALT: {alt_text}] "))
            else:
                img.decompose()

        # 5. Convert remaining DOM body to structured Markdown
        root = soup.body if soup.body else soup
        markdown_lines = self._node_to_markdown_lines(root)
        body_markdown = "\n".join(markdown_lines)

        # Append surfaced hidden modal / terms sections if not already verbatim in body_markdown
        appended_modals = 0
        extra_sections: List[str] = []
        for block_text in surfaced_blocks:
            if block_text not in body_markdown:
                appended_modals += 1
                extra_sections.append(f"- {block_text}")

        if extra_sections:
            body_markdown += (
                "\n\n## [TEXTO DE MODALES Y TÉRMINOS OCULTOS EN DOM]\n"
                + "\n".join(extra_sections)
            )

        # Collapse excessive blank lines while preserving clean section breaks
        body_markdown = re.sub(r"[ \t]+\n", "\n", body_markdown)
        body_markdown = re.sub(r"\n{3,}", "\n\n", body_markdown).strip()

        if metadata_header:
            header_lines = ["---"]
            for key, val in metadata_header.items():
                header_lines.append(f"{key}: {val}")
            header_lines.append("---\n")
            final_markdown = "\n".join(header_lines) + "\n" + body_markdown
        else:
            final_markdown = body_markdown

        if output_md_path is not None:
            output_md_path.parent.mkdir(parents=True, exist_ok=True)
            output_md_path.write_text(final_markdown, encoding="utf-8")

        return CleanedDOMArtifact(
            markdown_text=final_markdown,
            markdown_path=output_md_path,
            char_count=len(final_markdown),
            surfaced_modals_count=appended_modals,
        )

    @staticmethod
    def _normalize_inline_whitespace(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    def _table_to_markdown(self, table_tag: Tag) -> List[str]:
        rows_md: List[str] = []
        rows = table_tag.find_all("tr")
        for idx, tr in enumerate(rows):
            cells = tr.find_all(["th", "td"])
            if not cells:
                continue
            cell_texts = [
                self._normalize_inline_whitespace(c.get_text(" ", strip=True)).replace("|", "/")
                for c in cells
            ]
            if not any(cell_texts):
                continue
            rows_md.append("| " + " | ".join(cell_texts) + " |")
            if idx == 0:
                rows_md.append("| " + " | ".join(["---"] * len(cell_texts)) + " |")
        return rows_md

    def _node_to_markdown_lines(self, node: Tag) -> List[str]:
        lines: List[str] = []

        for child in node.children:
            if isinstance(child, NavigableString):
                txt = self._normalize_inline_whitespace(str(child))
                if txt:
                    lines.append(txt)
                continue

            if not isinstance(child, Tag):
                continue

            name = child.name.lower()

            if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                level = int(name[1])
                heading_txt = self._normalize_inline_whitespace(child.get_text(" ", strip=True))
                if heading_txt:
                    lines.append(f"\n{'#' * level} {heading_txt}\n")

            elif name == "table":
                table_lines = self._table_to_markdown(child)
                if table_lines:
                    lines.append("")
                    lines.extend(table_lines)
                    lines.append("")

            elif name in {"ul", "ol"}:
                lines.append("")
                for li in child.find_all("li", recursive=False):
                    li_txt = self._normalize_inline_whitespace(li.get_text(" ", strip=True))
                    if li_txt:
                        lines.append(f"- {li_txt}")
                lines.append("")

            elif name == "li":
                li_txt = self._normalize_inline_whitespace(child.get_text(" ", strip=True))
                if li_txt:
                    lines.append(f"- {li_txt}")

            elif name in {"p", "summary", "figcaption", "blockquote"}:
                p_txt = self._normalize_inline_whitespace(child.get_text(" ", strip=True))
                if p_txt:
                    lines.append(f"{p_txt}\n")

            elif name == "hr":
                lines.append("\n---\n")

            elif name in {"article", "section"}:
                nested = self._node_to_markdown_lines(child)
                if nested:
                    lines.append("\n---")
                    lines.extend(nested)

            else:
                classes_str = " ".join(child.get("class") or []).lower()
                is_card = any(
                    tok in classes_str for tok in ("card", "plan-item", "offer-box", "pricing-box", "tariff")
                )
                nested = self._node_to_markdown_lines(child)
                if nested:
                    if is_card:
                        lines.append("\n---")
                    lines.extend(nested)

        return lines
