/* Carrusel de «Próximo enfrentamiento» del Inicio (core/templates/home.html).
   El más cercano va delante y el siguiente asoma por detrás. Se cambia de tarjeta con el selector de
   abajo (una pastilla por tarjeta), con las flechas, arrastrando (la tarjeta sigue al dedo), tocando
   la que asoma o con las flechas del teclado. */
(function () {
    'use strict';
    var DRAG_START = 8;   // px que hay que mover antes de considerarlo un arrastre
    var DRAG_CHANGE = 60; // px a partir de los que se cambia de tarjeta

    document.querySelectorAll('[data-next-deck]').forEach(function (deck) {
        var slides = Array.prototype.slice.call(deck.querySelectorAll('[data-next-slide]'));
        var chips = Array.prototype.slice.call(deck.querySelectorAll('[data-next-dot]'));
        var prevBtn = deck.querySelector('[data-next-prev]');
        var nextBtn = deck.querySelector('[data-next-next]');
        var track = deck.querySelector('.z-next-deck-track');
        if (slides.length < 2 || !track) { return; }
        var index = 0;
        var startX = null;
        var dragging = false;
        var justDragged = false;

        function render() {
            slides.forEach(function (slide, k) {
                slide.classList.toggle('is-front', k === index);
                slide.classList.toggle('is-next', k === index + 1);
                slide.classList.toggle('is-prev', k === index - 1);
                slide.setAttribute('aria-hidden', k === index ? 'false' : 'true');
                if (k === index) { slide.removeAttribute('inert'); } else { slide.setAttribute('inert', ''); }
            });
            chips.forEach(function (chip, k) { chip.setAttribute('aria-current', k === index ? 'true' : 'false'); });
            deck.setAttribute('data-pos', index === 0 ? 'first' : (index === slides.length - 1 ? 'last' : 'mid'));
            if (prevBtn) { prevBtn.disabled = index === 0; }
            if (nextBtn) { nextBtn.disabled = index === slides.length - 1; }
        }
        function go(n) {
            index = Math.max(0, Math.min(slides.length - 1, n));
            render();
        }
        function front() { return slides[index]; }
        function endDrag() {
            deck.classList.remove('is-dragging');
            front().style.transform = '';
            dragging = false;
            startX = null;
        }

        chips.forEach(function (chip, k) { chip.addEventListener('click', function () { go(k); }); });
        if (prevBtn) { prevBtn.addEventListener('click', function () { go(index - 1); }); }
        if (nextBtn) { nextBtn.addEventListener('click', function () { go(index + 1); }); }

        track.addEventListener('pointerdown', function (e) { startX = e.clientX; dragging = false; justDragged = false; });
        track.addEventListener('pointermove', function (e) {
            if (startX === null) { return; }
            var dx = e.clientX - startX;
            if (!dragging && Math.abs(dx) > DRAG_START) {
                dragging = true;
                deck.classList.add('is-dragging');
                if (track.setPointerCapture) { try { track.setPointerCapture(e.pointerId); } catch (err) { /* sin captura */ } }
            }
            if (dragging) {
                // Al borde (sin tarjeta en ese lado) cuesta más moverla.
                var blocked = (dx > 0 && index === 0) || (dx < 0 && index === slides.length - 1);
                front().style.transform = 'translateX(' + Math.round(dx * (blocked ? 0.2 : 0.6)) + 'px)';
            }
        });
        track.addEventListener('pointerup', function (e) {
            if (startX === null) { return; }
            var dx = e.clientX - startX;
            var wasDragging = dragging;
            endDrag();
            if (wasDragging) {
                justDragged = true;
                if (Math.abs(dx) > DRAG_CHANGE) { go(index + (dx < 0 ? 1 : -1)); }
            }
        });
        track.addEventListener('pointercancel', endDrag);
        track.addEventListener('click', function (e) {
            var slide = e.target.closest('[data-next-slide]');
            if (justDragged) { e.preventDefault(); e.stopPropagation(); justDragged = false; return; }
            if (slide && !slide.classList.contains('is-front')) { go(slides.indexOf(slide)); }
        }, true);
        deck.addEventListener('keydown', function (e) {
            if (e.target.closest('input, textarea, select')) { return; }
            if (e.key === 'ArrowRight') { go(index + 1); }
            if (e.key === 'ArrowLeft') { go(index - 1); }
        });
        render();
    });
})();
