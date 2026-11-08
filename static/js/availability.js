/* Enlace de disponibilidad: botón «Copiar enlace» del capitán. */
(function () {
    "use strict";

    document.querySelectorAll("[data-availability-copy]").forEach(function (button) {
        var label = button.textContent;
        button.addEventListener("click", function () {
            var input = document.getElementById(button.getAttribute("data-availability-copy"));
            if (!input) { return; }
            input.select();
            var done = function () {
                button.textContent = button.getAttribute("data-copied") || label;
                setTimeout(function () { button.textContent = label; }, 2000);
            };
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(input.value).then(done);
            } else {
                document.execCommand("copy");
                done();
            }
        });
    });
})();
