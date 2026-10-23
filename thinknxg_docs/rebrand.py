"""Rebranding engine: Frappe / ERPNext → thinkNXG.

Pure Python core. Markdown is tokenized so that

* fenced code blocks and inline code are never touched (``frappe.get_doc`` stays valid),
* URLs are never text-replaced (``https://frappe.io`` does not become ``https://thinkNXG.io``),
  but link targets *are* rewritten by URL rules (docs.frappe.io/erpnext/x → /thinknxgerp/x),
* product names in prose, headings, link text, image alt text and HTML alt/title attributes
  are replaced in a single pass, longest name first, so rules never cascade.
"""

import re

from thinknxg_docs.source_parser import normalize_slug

DEFAULT_TEXT_RULES = [
    # find, replace, match_case, whole_word
    ("Frappe Framework", "thinkNXG Framework", 1, 1),
    ("Frappe HR", "thinkNXG HR", 1, 1),
    ("FrappeHR", "thinkNXG HR", 1, 1),
    ("Frappe Cloud", "thinkNXG Cloud", 1, 1),
    ("FrappeCloud", "thinkNXG Cloud", 1, 1),
    ("ERPNext", "thinkNXG ERP", 1, 1),
    ("ERPNEXT", "thinkNXG ERP", 1, 1),
    ("Erpnext", "thinkNXG ERP", 1, 1),
    ("Frappe", "thinkNXG", 1, 1),
    ("FRAPPE", "thinkNXG", 1, 1),
]

DEFAULT_SPACES = [
    # route, title, upstream base, published
    ("thinknxgerp", "thinkNXG ERP", "https://docs.frappe.io/erpnext", 1),
    ("thinknxghr", "thinkNXG HR", "https://docs.frappe.io/hr", 0),
    ("thinknxgframework", "thinkNXG Framework", "https://docs.frappe.io/framework", 0),
    ("thinknxgcloud", "thinkNXG Cloud", "https://docs.frappe.io/cloud", 0),
]

_W = "A-Za-z0-9_"

_TOKEN_RE = re.compile(
    r"(?P<fence>^[ \t]{0,3}(?P<fchar>`{3,}|~{3,})[^\n]*\n(?:[^\n]*\n)*?[ \t]{0,3}(?P=fchar)[ \t]*$)"
    r"|(?P<icode>``[^\n]*?``|`[^`\n]+`)"
    r"|(?P<refdef>^[ \t]{0,3}\[[^\]\n]+\]:[ \t]*(?P<refurl><[^>\n]*>|\S+)[^\n]*$)"
    r"|(?P<mdlink>\]\((?P<mdurl><[^>\n]*>|[^)\s]*)(?P<mdtitle>\s+\"[^\"\n]*\")?\))"
    r"|(?P<autolink><(?P<autourl>https?://[^>\s]+)>)"
    r"|(?P<html></?[A-Za-z][^>\n]*>)"
    r"|(?P<bare>https?://[^\s<>()\[\]\"'`]+)",
    re.M,
)
_ATTR_URL_RE = re.compile(r"(\b(?:href|src)\s*=\s*)([\"'])(.*?)\2", re.I)
_ATTR_TEXT_RE = re.compile(r"(\b(?:alt|title)\s*=\s*)([\"'])(.*?)\2", re.I)


class Rebrander:
    """Apply text + URL rebranding.

    text_rules: iterable of (find, replace, match_case, whole_word) or dicts with those keys
    url_rules:  iterable of (find_prefix, replace_prefix) — plain prefix replacement
    space_maps: iterable of (source_base, target_prefix), e.g.
                ("https://docs.frappe.io/erpnext", "/thinknxgerp") — slug-aware rewrite
    slug_resolver: optional callable(target_prefix, slug) -> slug for fixing renamed/moved pages
    """

    def __init__(self, text_rules=None, url_rules=None, space_maps=None, slug_resolver=None):
        rules = []
        for r in (DEFAULT_TEXT_RULES if text_rules is None else text_rules):
            if isinstance(r, dict):
                r = (r.get("find_text") or r.get("find"), r.get("replace_with") or r.get("replace") or "",
                     r.get("match_case", 1), r.get("whole_word", 1))
            find, repl, case, word = (list(r) + [1, 1])[:4]
            if find:
                rules.append((find, repl or "", int(case or 0), int(word or 0)))
        rules.sort(key=lambda x: len(x[0]), reverse=True)
        self._repl = {}
        parts = []
        for i, (find, repl, case, word) in enumerate(rules):
            pat = re.escape(find)
            if word:
                if re.match(rf"[{_W}]", find[0]):
                    pat = rf"(?<![{_W}])" + pat
                if re.match(rf"[{_W}]", find[-1]):
                    pat = pat + rf"(?![{_W}])"
            if not case:
                pat = f"(?i:{pat})"
            name = f"r{i}"
            parts.append(f"(?P<{name}>{pat})")
            self._repl[name] = repl
        self._text_re = re.compile("|".join(parts)) if parts else None

        self.url_rules = sorted([(a, b or "") for a, b in (url_rules or []) if a],
                                key=lambda x: len(x[0]), reverse=True)
        maps = []
        for base, target in space_maps or []:
            base = (base or "").rstrip("/")
            if not base:
                continue
            variants = {base}
            if base.startswith("https://"):
                variants.add("http://" + base[8:])
            for v in variants:
                maps.append((v, (target or "").rstrip("/")))
        self.space_maps = sorted(maps, key=lambda x: len(x[0]), reverse=True)
        self.slug_resolver = slug_resolver

    # ----------------------------------------------------------- text
    def text(self, s):
        if not s or not self._text_re:
            return s
        return self._text_re.sub(lambda m: self._repl[m.lastgroup], s)

    # ------------------------------------------------------------ url
    def url(self, u):
        if not u:
            return u
        for base, target in self.space_maps:
            if u == base or (u.startswith(base) and u[len(base)] in "/#?"):
                rest = u[len(base):]
                tail = ""
                cut = min([i for i in (rest.find("#"), rest.find("?")) if i >= 0], default=-1)
                if cut >= 0:
                    rest, tail = rest[:cut], rest[cut:]
                path = rest.strip("/")
                if path.lower() == "llms.txt":
                    return f"{target}/llms.txt{tail}"
                slug = normalize_slug(path)
                if slug and self.slug_resolver:
                    slug = self.slug_resolver(target, slug) or slug
                return (f"{target}/{slug}" if slug else (target or "/")) + tail
        for find, repl in self.url_rules:
            if u.startswith(find):
                return repl + u[len(find):]
        return u

    def _bare(self, u):
        trail = ""
        while u and u[-1] in ".,;:!?":
            trail = u[-1] + trail
            u = u[:-1]
        return self.url(u) + trail

    def _html(self, tag):
        tag = _ATTR_URL_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{self.url(m.group(3))}{m.group(2)}", tag)
        return _ATTR_TEXT_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{self.text(m.group(3))}{m.group(2)}", tag)

    # ------------------------------------------------------- markdown
    def markdown(self, md):
        if not md:
            return md
        out, pos = [], 0
        for m in _TOKEN_RE.finditer(md):
            out.append(self.text(md[pos:m.start()]))
            kind = _first_group(m)
            tok = m.group(0)
            if kind in ("fence", "icode"):
                out.append(tok)
            elif kind == "mdlink":
                raw = m.group("mdurl")
                angle = raw.startswith("<") and raw.endswith(">")
                u = self.url(raw[1:-1] if angle else raw)
                title = m.group("mdtitle") or ""
                out.append("](" + (f"<{u}>" if angle else u) + self.text(title) + ")")
            elif kind == "refdef":
                raw = m.group("refurl")
                angle = raw.startswith("<") and raw.endswith(">")
                u = self.url(raw[1:-1] if angle else raw)
                s, e = m.start("refurl") - m.start(), m.end("refurl") - m.start()
                out.append(tok[:s] + (f"<{u}>" if angle else u) + self.text(tok[e:]))
            elif kind == "autolink":
                out.append("<" + self.url(m.group("autourl")) + ">")
            elif kind == "html":
                out.append(self._html(tok))
            else:
                out.append(self._bare(tok))
            pos = m.end()
        out.append(self.text(md[pos:]))
        return "".join(out)


def _first_group(m):
    for k in ("fence", "icode", "refdef", "mdlink", "autolink", "html", "bare"):
        if m.group(k) is not None:
            return k
    return None
