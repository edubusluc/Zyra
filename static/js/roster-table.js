/*
 * Tabla de plantilla (Estadísticas · Equipo y Jugadores): paginador, orden y lado cambian solo la tabla.
 * Pide la misma URL, sustituye el contenido de la tarjeta y actualiza la dirección. Sin JS o si la petición
 * falla, los enlaces funcionan como siempre (recarga completa).
 */
(function () {
  'use strict';
  var SELECTOR = '.st-roster';

  function swap(url, push) {
    var card = document.querySelector(SELECTOR);
    if (!card) { return Promise.reject(new Error('sin tabla')); }
    card.setAttribute('aria-busy', 'true');
    return fetch(url, {credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}})
      .then(function (res) {
        if (!res.ok) { throw new Error('http ' + res.status); }
        return res.text();
      })
      .then(function (html) {
        var fresh = new DOMParser().parseFromString(html, 'text/html').querySelector(SELECTOR);
        if (!fresh) { throw new Error('sin tabla en la respuesta'); }
        card.innerHTML = fresh.innerHTML;
        if (push) { history.pushState({roster: true}, '', url); }
        card.removeAttribute('aria-busy');
        var table = card.querySelector('.st-table-wrap') || card;
        var top = table.getBoundingClientRect().top;
        if (top < 0) { card.scrollIntoView({block: 'start'}); }
      })
      .catch(function () { window.location.href = url; });
  }

  document.addEventListener('click', function (event) {
    var link = event.target.closest ? event.target.closest(SELECTOR + ' a[href]') : null;
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey ||
        event.shiftKey || event.altKey || link.target) { return; }
    var target = new URL(link.href, window.location.href);
    if (target.origin !== window.location.origin || target.pathname !== window.location.pathname ||
        target.searchParams.has('player')) { return; }
    event.preventDefault();
    swap(target.href, true);
  }, true);  // captura: page-transitions.js ve el clic cancelado y no atenúa la página

  window.addEventListener('popstate', function () {
    if (document.querySelector(SELECTOR)) { swap(window.location.href, false); }
  });
})();
