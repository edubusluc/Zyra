"""Los globos «i» (``.z-tip``) usan siempre la misma fuente: la de cuerpo, peso normal, sin heredar la del título."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS = Path(settings.BASE_DIR, 'static', 'style.css')


def _reglas_del_globo():
    """Reglas CSS cuyo selector toca el globo (``.z-tip`` con ``::after``)."""
    texto = re.sub(r'/\*.*?\*/', '', CSS.read_text(encoding='utf-8'), flags=re.S)
    for selector, cuerpo in re.findall(r'([^{}]+)\{([^{}]*)\}', texto):
        if '.z-tip' in selector and '::after' in selector:
            yield selector.strip(), cuerpo


class TooltipFontTests(SimpleTestCase):
    def test_globo_base_usa_la_fuente_unica(self):
        base = [c for s, c in _reglas_del_globo() if s == '.z-tip::after']
        self.assertGreaterEqual(len(base), 1)  # la versión móvil repite el selector
        self.assertIn('font: var(--z-tip-font)', base[0])
        self.assertIn('text-transform: none', base[0])
        self.assertIn('letter-spacing: normal', base[0])

    def test_fuente_unica_es_cuerpo_y_peso_normal(self):
        texto = CSS.read_text(encoding='utf-8')
        m = re.search(r'--z-tip-font:\s*([^;]+);', texto)
        self.assertIsNotNone(m)
        self.assertRegex(m.group(1), r'^400\b')
        self.assertIn('var(--z-body)', m.group(1))

    def test_ninguna_variante_cambia_familia_peso_ni_mayusculas(self):
        for selector, cuerpo in _reglas_del_globo():
            for prop in ('font-family', 'font-weight', 'text-transform', 'letter-spacing'):
                if selector == '.z-tip::after' and prop in ('text-transform', 'letter-spacing'):
                    continue
                self.assertNotRegex(cuerpo, rf'(^|;)\s*{prop}\s*:', f'{selector} redefine {prop}')
