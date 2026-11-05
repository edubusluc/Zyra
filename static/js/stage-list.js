/* Lista de la tarjeta enfocada de la ficha (apuntados, convocados o parejas): si es más larga que
   la tarjeta, se desplaza por dentro, se puede enfocar con el teclado para recorrerla y se deja a
   la vista tu propia fila. Sin JS se ven todas las filas con el desplazamiento del navegador. */
(function () {
    document.querySelectorAll('[data-stage-list]').forEach(function (list) {
        if (list.scrollHeight <= list.clientHeight) { return; }
        list.setAttribute('tabindex', '0');
        var section = list.closest('section');
        if (section) { list.setAttribute('aria-label', section.getAttribute('aria-label') || ''); }
        var me = list.querySelector('.is-me');
        if (me) { list.scrollTop = Math.max(0, me.offsetTop - list.offsetTop - list.clientHeight / 3); }
    });
})();
