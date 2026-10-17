"""
Saneado del HTML que escribe el personal en el editor de «Escribir al capitán».

El navegador nunca es de fiar: el HTML se reconstruye en el servidor con una lista blanca de etiquetas
(párrafos, negrita, cursiva, título, listas, cita y enlace), sin atributos salvo ``href`` en enlaces
``http``, ``https`` o ``mailto``. Todo lo demás se descarta conservando solo el texto.
"""
import re
from html import escape
from html.parser import HTMLParser

# Etiqueta de entrada -> etiqueta de salida (None = se descarta la etiqueta pero se conserva el texto).
_TAGS = {
    "p": "p", "div": "p", "br": "br",
    "strong": "strong", "b": "strong", "em": "em", "i": "em",
    "h1": "h2", "h2": "h2", "h3": "h3",
    "ul": "ul", "ol": "ol", "li": "li", "blockquote": "blockquote", "a": "a",
}
_VOID = {"br"}
_DROP_CONTENT = {"script", "style", "head", "title", "template", "iframe", "object", "noscript"}
_SAFE_URL = re.compile(r"^(https?://|mailto:)", re.IGNORECASE)
_BLOCKS = {"p", "h2", "h3", "ul", "ol", "li", "blockquote"}
_STYLES = {
    "p": "margin:0 0 14px;",
    "h2": "margin:0 0 12px; font-size:20px; line-height:1.3;",
    "h3": "margin:0 0 10px; font-size:17px; line-height:1.3;",
    "ul": "margin:0 0 14px; padding-left:22px;",
    "ol": "margin:0 0 14px; padding-left:22px;",
    "blockquote": "margin:0 0 14px; padding-left:12px; border-left:3px solid #B4F100; color:#555;",
}


class _Sanitizer(HTMLParser):
    """Reconstruye el HTML solo con lo permitido."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.stack = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _DROP_CONTENT:
            self.skip += 1
            return
        mapped = _TAGS.get(tag)
        if self.skip or not mapped:
            return
        if mapped in _VOID:
            self.out.append("<br>")
            return
        attr_text = ""
        if mapped == "a":
            href = (dict(attrs).get("href") or "").strip()
            if _SAFE_URL.match(href):
                attr_text = ' href="%s" style="color:#4d6b00;" rel="noopener noreferrer"' % escape(href, quote=True)
            else:
                mapped = None  # enlace sin destino seguro: solo queda el texto
        elif mapped in _STYLES:
            attr_text = ' style="%s"' % _STYLES[mapped]
        self.stack.append(mapped)
        if mapped:
            self.out.append("<%s%s>" % (mapped, attr_text))

    def handle_endtag(self, tag):
        if tag in _DROP_CONTENT:
            self.skip = max(0, self.skip - 1)
            return
        mapped = _TAGS.get(tag)
        if self.skip or not mapped or mapped in _VOID:
            return
        if tag == "a" or mapped in self.stack:
            # Cierra hasta la etiqueta abierta correspondiente (HTML mal anidado).
            while self.stack:
                top = self.stack.pop()
                if top:
                    self.out.append("</%s>" % top)
                if top == mapped or (top is None and tag == "a"):
                    break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(escape(data, quote=False))

    def close(self):
        super().close()
        while self.stack:
            top = self.stack.pop()
            if top:
                self.out.append("</%s>" % top)


def looks_like_html(text):
    """True si el texto trae etiquetas HTML (lo normal con el editor); si no, es texto plano."""
    return bool(re.search(r"</?[a-zA-Z][^>]*>", text))


def plain_to_html(text):
    """Convierte texto plano en párrafos HTML (una línea en blanco separa párrafos)."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    return "".join("<p>%s</p>" % escape(p).replace("\n", "<br>") for p in paragraphs)


def sanitize_html(raw):
    """Devuelve el HTML saneado con estilos en línea aptos para correo."""
    if not looks_like_html(raw):
        raw = plain_to_html(raw)
    parser = _Sanitizer()
    parser.feed(raw)
    parser.close()
    html = "".join(parser.out)
    # Texto suelto fuera de bloques: lo envolvemos en un párrafo.
    if html and not re.match(r"\s*<(p|h2|h3|ul|ol|blockquote)\b", html):
        html = '<p style="%s">%s</p>' % (_STYLES["p"], html)
    return html


def html_to_text(html):
    """Texto plano equivalente al HTML saneado, para la alternativa de texto del correo."""
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"<li\b[^>]*>", "\n- ", text)
    text = re.sub(r"<a\b[^>]*href=\"([^\"]*)\"[^>]*>(.*?)</a>", lambda m: "%s (%s)" % (m.group(2), m.group(1)), text, flags=re.S)
    text = re.sub(r"</(p|h2|h3|ul|ol|blockquote)>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    from html import unescape
    return re.sub(r"\n{3,}", "\n\n", unescape(text)).strip()
