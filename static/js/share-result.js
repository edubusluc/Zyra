/*
 * «Compartir resultado» y «Compartir alineación»: en el móvil abre el menú de compartir del sistema con la imagen del resultado
 * (y el texto); en el ordenador descarga la imagen y abre WhatsApp con el texto, para adjuntarla.
 * Sin JavaScript el botón sigue siendo un enlace a WhatsApp con el texto.
 */
(function () {
    if (window.zShareResultReady) { return; }
    window.zShareResultReady = true;

    function download(blob, name) {
        var url = URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = url;
        link.download = name;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
    }

    function fetchImage(url) {
        return fetch(url, { credentials: 'same-origin' }).then(function (r) {
            if (!r.ok) { throw new Error('image'); }
            return r.blob();
        });
    }

    document.addEventListener('click', function (event) {
        var button = event.target.closest('[data-share-image]');
        if (!button || !window.fetch) { return; }
        var url = button.dataset.shareImage;
        var text = button.dataset.shareText || '';
        var name = button.dataset.shareFile || 'resultado-zyra.jpg';
        if (!(navigator.canShare && navigator.share)) {
            // Ordenador sin menú de compartir: el enlace abre WhatsApp y la imagen se descarga a la vez.
            fetchImage(url).then(function (blob) { download(blob, name); }).catch(function () {});
            return;
        }
        event.preventDefault();
        fetchImage(url).then(function (blob) {
            var file = new File([blob], name, { type: 'image/jpeg' });
            if (!navigator.canShare({ files: [file] })) {
                download(blob, name);
                window.open(button.href, '_blank', 'noopener');
                return null;
            }
            return navigator.share({ files: [file], text: text });
        }).catch(function (error) {
            if (error && error.name === 'AbortError') { return; }
            window.open(button.href, '_blank', 'noopener');
        });
    });
})();
