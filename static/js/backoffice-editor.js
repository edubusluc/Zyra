/* Editor sencillo del campo Mensaje de «Escribir al capitán»: negrita, cursiva, título, listas y enlace.
   El HTML se envía tal cual, pero el servidor lo vuelve a sanear (backoffice/richtext.py). */
(function () {
    var form = document.getElementById("contact-form");
    if (!form) { return; }
    var editor = document.getElementById("contact-editor");
    var field = document.getElementById("contact-body");
    var templates = JSON.parse(document.getElementById("contact-templates").textContent);

    function esc(text) {
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
    function plainToHtml(text) {
        return text.split(/\n\s*\n/).filter(function (p) { return p.trim(); }).map(function (p) {
            return "<p>" + esc(p.trim()).replace(/\n/g, "<br>") + "</p>";
        }).join("");
    }

    document.querySelectorAll("[data-editor-cmd]").forEach(function (button) {
        button.addEventListener("mousedown", function (event) { event.preventDefault(); });
        button.addEventListener("click", function () {
            var cmd = button.dataset.editorCmd;
            editor.focus();
            if (cmd === "link") {
                var url = window.prompt(button.dataset.prompt, "https://");
                if (url) { document.execCommand("createLink", false, url); }
            } else if (cmd === "h2") {
                document.execCommand("formatBlock", false, "h2");
            } else if (cmd === "p") {
                document.execCommand("formatBlock", false, "p");
            } else {
                document.execCommand(cmd, false, null);
            }
        });
    });

    document.getElementById("contact-template").addEventListener("change", function () {
        var t = templates[this.value] || {subject: "", body: ""};
        document.getElementById("contact-subject").value = t.subject;
        editor.innerHTML = plainToHtml(t.body);
    });

    form.addEventListener("submit", function (event) {
        field.value = editor.innerHTML;
        if (!editor.textContent.trim()) {
            event.preventDefault();
            editor.focus();
        }
    });
})();
