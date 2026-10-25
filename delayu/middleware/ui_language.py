"""Подмена русского текста интерфейса, когда в шапке выбран английский."""
from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

from delayu.ui_phrases import PHRASES

_ORDERED = sorted(PHRASES, key=len, reverse=True)
_LOOKUP: dict[str, str] = {}
for _key in _ORDERED:
    _LOOKUP.setdefault(_key.casefold(), PHRASES[_key])
_PATTERN = re.compile(
    r"(?<![A-Za-zА-Яа-яЁё])(?:"
    + "|".join(re.escape(item) for item in _ORDERED)
    + r")(?![A-Za-zА-Яа-яЁё])",
    re.IGNORECASE,
)
_ATTRS = {"title", "placeholder", "aria-label", "alt"}
_SKIP = {"script", "style", "noscript"}
_VOID = {
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
    "source",
    "track",
    "wbr",
}


def translate_fragment(text: str) -> str:
    if not text or not _PATTERN.search(text):
        return text
    return _PATTERN.sub(lambda match: _LOOKUP[match.group(0).casefold()], text)


class _Rewriter(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_tags: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP or (self._locked(attrs) and tag not in _VOID):
            self.skip_tags.append(tag)
        self.parts.append(self._start(tag, attrs, False))

    def handle_startendtag(self, tag, attrs):
        self.parts.append(self._start(tag, attrs, True))

    def handle_endtag(self, tag):
        self.parts.append(f"</{tag}>")
        if self.skip_tags and self.skip_tags[-1] == tag:
            self.skip_tags.pop()

    def handle_data(self, data):
        text = data if self.skip_tags else translate_fragment(data)
        self.parts.append(escape(text, quote=False))

    def handle_comment(self, data):
        self.parts.append(f"<!--{data}-->")

    def handle_decl(self, decl):
        self.parts.append(f"<!{decl}>")

    def handle_pi(self, data):
        self.parts.append(f"<?{data}>")

    def _start(self, tag: str, attrs, empty: bool) -> str:
        chunks = [f"<{tag}"]
        for key, value in attrs:
            if value is None:
                chunks.append(f" {key}")
                continue
            if key == "lang" and value.startswith("ru"):
                value = "en"
            elif key == "value" and not self.skip_tags and not self._locked(attrs):
                replacement = _LOOKUP.get(value.strip().casefold())
                if replacement:
                    value = replacement
            elif key in _ATTRS and not self.skip_tags and not self._locked(attrs):
                value = translate_fragment(value)
            safe = escape(value, quote=True)
            chunks.append(f' {key}="{safe}"')
        chunks.append(" />" if empty else ">")
        return "".join(chunks)

    @staticmethod
    def _locked(attrs) -> bool:
        return any(key == "translate" and value == "no" for key, value in attrs)


def translate_html(html: str) -> str:
    parser = _Rewriter()
    parser.feed(html)
    parser.close()
    return "".join(parser.parts)


class UiLanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        language = getattr(request, "LANGUAGE_CODE", "") or ""
        if not str(language).lower().startswith("en"):
            return response
        content_type = response.get("Content-Type", "")
        if "text/html" not in content_type or getattr(response, "streaming", False):
            return response
        charset = response.charset or "utf-8"
        try:
            html = response.content.decode(charset)
            translated = translate_html(html)
        except (LookupError, UnicodeDecodeError, ValueError):
            return response
        response.content = translated.encode(charset)
        if response.get("Content-Length"):
            response["Content-Length"] = str(len(response.content))
        response["Content-Language"] = "en"
        return response
