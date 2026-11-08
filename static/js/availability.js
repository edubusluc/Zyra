/* Enlace de disponibilidad: botón «Copiar enlace» del capitán y comentario de «Aún no sé» en la respuesta del jugador. */
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

    document.querySelectorAll("[data-availability]").forEach(function (form) {
        var box = form.querySelector("[data-availability-comment]");
        form.addEventListener("change", function () {
            var checked = form.querySelector("input[name=answer]:checked");
            box.hidden = !(checked && checked.value === "maybe");
            form.querySelectorAll(".z-segmented .btn").forEach(function (label) {
                var input = label.querySelector("input");
                label.classList.toggle("active", input.checked);
            });
        });
    });
})();
