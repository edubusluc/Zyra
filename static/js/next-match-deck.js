/* Carrusel de «Próximo enfrentamiento» del Inicio (core/templates/home.html).
   El más cercano va delante y el siguiente asoma por detrás; los puntos, el gesto de deslizar, tocar
   la tarjeta que asoma y las flechas del teclado cambian de tarjeta. */
(function () {
    'use strict';
    document.querySelectorAll('[data-next-deck]').forEach(function (deck) {
        var slides = Array.prototype.slice.call(deck.querySelectorAll('[data-next-slide]'));
        var dots = Array.prototype.slice.call(deck.querySelectorAll('[data-next-dot]'));
        var track = deck.querySelector('.z-next-deck-track');
        if (slides.length < 2 || !track) { return; }
        var index = 0;
        var startX = null;
        var swiped = false;

        function render() {
            slides.forEach(function (slide, k) {
                slide.classList.toggle('is-front', k === index);
                slide.classList.toggle('is-next', k === index + 1);
                slide.classList.toggle('is-prev', k === index - 1);
                slide.setAttribute('aria-hidden', k === index ? 'false' : 'true');
                if (k === index) { slide.removeAttribute('inert'); } else { slide.setAttribute('inert', ''); }
            });
            dots.forEach(function (dot, k) { dot.setAttribute('aria-current', k === index ? 'true' : 'false'); });
            deck.classList.toggle('has-prev', index > 0);
            deck.classList.toggle('has-next', index < slides.length - 1);
        }
        function go(n) {
            index = Math.max(0, Math.min(slides.length - 1, n));
            render();
        }

        dots.forEach(function (dot, k) { dot.addEventListener('click', function () { go(k); }); });
        track.addEventListener('pointerdown', function (e) { startX = e.clientX; swiped = false; });
        track.addEventListener('pointerup', function (e) {
            if (startX === null) { return; }
            var dx = e.clientX - startX;
            startX = null;
            if (Math.abs(dx) > 40) { swiped = true; go(index + (dx < 0 ? 1 : -1)); }
        });
        track.addEventListener('pointercancel', function () { startX = null; });
        track.addEventListener('click', function (e) {
            var slide = e.target.closest('[data-next-slide]');
            if (!swiped && slide && !slide.classList.contains('is-front')) { go(slides.indexOf(slide)); }
            swiped = false;
        });
        deck.addEventListener('keydown', function (e) {
            if (e.target.closest('input, textarea, select')) { return; }
            if (e.key === 'ArrowRight') { go(index + 1); }
            if (e.key === 'ArrowLeft') { go(index - 1); }
        });
        render();
    });
})();
