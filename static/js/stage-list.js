/* Paginación de la lista de la ficha del enfrentamiento (apuntados, convocados o parejas):
   muestra PAGE filas y un selector «‹ 1/3 ›». Sin JS se ven todas. */
(function () {
    var PAGE = 6;
    document.querySelectorAll('[data-stage-list]').forEach(function (list) {
        var rows = Array.prototype.slice.call(list.children);
        if (rows.length <= PAGE) { return; }
        var pages = Math.ceil(rows.length / PAGE);
        var me = rows.findIndex(function (r) { return r.classList.contains('is-me'); });
        var page = me < 0 ? 0 : Math.floor(me / PAGE);
        var nav = document.createElement('div');
        nav.className = 'z-stage-pager';
        nav.innerHTML = '<button type="button" class="z-stage-prev" aria-label="' + (list.dataset.prev || 'Anterior') + '"><i class="fa-solid fa-chevron-left" aria-hidden="true"></i></button>' +
            '<span aria-live="polite"></span>' +
            '<button type="button" class="z-stage-next" aria-label="' + (list.dataset.next || 'Siguiente') + '"><i class="fa-solid fa-chevron-right" aria-hidden="true"></i></button>';
        list.after(nav);
        var label = nav.querySelector('span');
        var prev = nav.querySelector('.z-stage-prev');
        var next = nav.querySelector('.z-stage-next');
        function show() {
            rows.forEach(function (r, i) { r.hidden = Math.floor(i / PAGE) !== page; });
            label.textContent = (page + 1) + ' / ' + pages;
            prev.disabled = page === 0;
            next.disabled = page === pages - 1;
        }
        prev.addEventListener('click', function () { page -= 1; show(); });
        next.addEventListener('click', function () { page += 1; show(); });
        show();
    });
})();
