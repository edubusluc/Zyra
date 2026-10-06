// Paso suave entre páginas. Al entrar, el contenido aparece con un fundido (style.css);
// al pulsar un enlace o enviar un formulario, el contenido se atenúa mientras carga la
// siguiente página. Nunca se bloquea ni se retrasa la navegación: no hay preventDefault
// ni pointer-events, así que un segundo clic rápido llega siempre a su destino.
(function () {
  const root = document.body;
  let restore = 0;

  function leaving() {
    root.classList.add('z-leaving');
    // Descargas (PDF de la convocatoria) o respuestas que no cambian de página:
    // si no se ha salido en un rato, se devuelve el contenido a su estado normal.
    clearTimeout(restore);
    restore = setTimeout(stay, 2500);
  }

  function stay() {
    clearTimeout(restore);
    root.classList.remove('z-leaving');
  }

  function isPageLink(link, event) {
    if (event.defaultPrevented || event.button !== 0) return false;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false;
    if (link.target && link.target !== '_self') return false;
    if (link.hasAttribute('download') || link.hasAttribute('data-bs-toggle')) return false;
    const href = link.getAttribute('href');
    if (!href || href.charAt(0) === '#' || /^(mailto|tel|javascript):/i.test(href)) return false;
    if (link.origin !== window.location.origin) return false;
    // Mismo documento con otra ancla: no hay carga de página
    return !(link.hash && link.pathname === window.location.pathname && link.search === window.location.search);
  }

  // Fase de burbuja: si otro script ha cancelado el clic o el envío, no se atenúa nada.
  document.addEventListener('click', function (event) {
    const link = event.target.closest && event.target.closest('a[href]');
    if (link && isPageLink(link, event)) leaving();
  });

  document.addEventListener('submit', function (event) {
    const form = event.target;
    if (event.defaultPrevented || (form.target && form.target !== '_self')) return;
    leaving();
  });

  // Volver con el botón Atrás (página guardada en caché): se ve normal, sin atenuar.
  window.addEventListener('pageshow', stay);
})();
