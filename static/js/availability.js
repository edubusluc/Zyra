/* Enlace de disponibilidad: botón «Copiar enlace» del capitán, con aviso para lectores de pantalla. */
(function () {
    "use strict";

    document.querySelectorAll("[data-availability-copy]").forEach(function (button) {
        var label = button.querySelector("[data-availability-copy-label]") || button;
        var original = label.textContent;
        var status = document.querySelector("[data-availability-copy-status]");
        var show = function (text) {
            label.textContent = text;
            if (status) { status.textContent = text; }
            setTimeout(function () {
                label.textContent = original;
                if (status) { status.textContent = ""; }
            }, 2500);
        };
        button.addEventListener("click", function () {
            var input = document.getElementById(button.getAttribute("data-availability-copy"));
            if (!input) { return; }
            input.select();
            var done = function () { show(button.getAttribute("data-copied") || original); };
            var failed = function () { show(button.getAttribute("data-failed") || original); };
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(input.value).then(done, failed);
            } else {
                try {
                    if (document.execCommand("copy")) { done(); } else { failed(); }
                } catch (e) { failed(); }
            }
        });
    });
})();
