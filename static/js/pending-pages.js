/* Selector de páginas del bloque «Pendiente» del Inicio (core/templates/home.html).
   Cada página reúne pocas filas (vencidos y próximos 14 días). Sin JS se ven todas; con JS se muestra una
   y el selector (flechas y números) cambia de página. */
(function () {
    'use strict';
    document.querySelectorAll('[data-pending-pages]').forEach(function (box) {
        var pages = Array.prototype.slice.call(box.querySelectorAll('[data-pending-page]'));
        var chips = Array.prototype.slice.call(box.querySelectorAll('[data-pending-dot]'));
        var picker = box.querySelector('[data-pending-picker]');
        var prevBtn = box.querySelector('[data-pending-prev]');
        var nextBtn = box.querySelector('[data-pending-next]');
        if (pages.length < 2 || !picker) { return; }
        var index = 0;

        function render() {
            pages.forEach(function (page, k) { page.hidden = k !== index; });
            chips.forEach(function (chip, k) { chip.setAttribute('aria-current', k === index ? 'true' : 'false'); });
            if (prevBtn) { prevBtn.disabled = index === 0; }
            if (nextBtn) { nextBtn.disabled = index === pages.length - 1; }
        }
        function go(n) {
            index = Math.max(0, Math.min(pages.length - 1, n));
            render();
        }

        picker.hidden = false;
        chips.forEach(function (chip, k) { chip.addEventListener('click', function () { go(k); }); });
        if (prevBtn) { prevBtn.addEventListener('click', function () { go(index - 1); }); }
        if (nextBtn) { nextBtn.addEventListener('click', function () { go(index + 1); }); }
        render();
    });
})();
