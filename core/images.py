"""
Fotos subidas por los usuarios (escudos de equipo y fotos de jugador).

Se guardan con el almacenamiento de Django (settings.STORAGES["default"]): en local, en la
carpeta media/ (MEDIA_ROOT), nunca en static/. Antes de guardarlas se procesan con Pillow:
se comprueba que son una imagen, se giran según la orientación EXIF del móvil, se reducen a
PHOTO_MAX_SIZE píxeles de lado como máximo y se guardan en WebP. Al volver a codificarlas se
pierden los metadatos (EXIF, ubicación GPS...).

Cuando una foto se cambia o se borra su equipo/jugador, el fichero antiguo se borra del
almacenamiento si ya no lo usa nadie más.
"""
import logging
import time
import uuid
from io import BytesIO

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.translation import gettext as _
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)
# Si procesar y validar una foto tarda más de esto (segundos) se anota en el log con el desglose.
SLOW_PHOTO_SECONDS = 1.0

# Carpetas del almacenamiento donde van las fotos. Las rutas que no empiezan por una de
# ellas son antiguas (static/team, static/profile): las mueve el comando move_photos_to_media.
TEAM_PHOTO_DIR = "teams"
PLAYER_PHOTO_DIR = "players"
PHOTO_DIRS = (TEAM_PHOTO_DIR, PLAYER_PHOTO_DIR)


def team_photo_path(instance, filename):
    """upload_to de los escudos de equipo: nombre aleatorio dentro de teams/."""
    return _random_name(TEAM_PHOTO_DIR, filename)


def player_photo_path(instance, filename):
    """upload_to de las fotos de jugador: nombre aleatorio dentro de players/."""
    return _random_name(PLAYER_PHOTO_DIR, filename)


def _random_name(folder, filename):
    """Nombre aleatorio: no choca con otras fotos ni deja ver el nombre del fichero original."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "webp"
    return f"{folder}/{uuid.uuid4().hex}.{ext}"


def process_image(source):
    """
    Lee una imagen (fichero subido o abierto) y devuelve un ContentFile .webp reducido.
    Lanza ValidationError si no es una imagen válida o es demasiado grande.
    """
    max_bytes = settings.PHOTO_MAX_UPLOAD_MB * 1024 * 1024
    if getattr(source, "size", None) and source.size > max_bytes:
        raise ValidationError(
            _("La imagen ocupa demasiado (máximo %(mb)s MB).") % {"mb": settings.PHOTO_MAX_UPLOAD_MB}
        )
    try:
        source.seek(0)
        with Image.open(source) as img:
            img.load()
            img = ImageOps.exif_transpose(img)
            # WebP admite transparencia (escudos PNG); el resto se pasa a RGB.
            has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
            img = img.convert("RGBA" if has_alpha else "RGB")
            img.thumbnail((settings.PHOTO_MAX_SIZE, settings.PHOTO_MAX_SIZE), Image.LANCZOS)
            out = BytesIO()
            # method=6 con transparencia (escudos PNG) tarda entre 1 y 8 s por foto y pesa lo mismo que 4.
            img.save(out, format="WEBP", quality=settings.PHOTO_WEBP_QUALITY, method=4)
    except (OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError(_("El archivo no es una imagen válida."))
    return ContentFile(out.getvalue(), name="photo.webp")


def clean_photo_field(form, field_name="photo"):
    """
    clean_<campo> de los formularios: procesa la foto recién subida, la valida con
    Rekognition (core/moderation.py) y deja las demás igual. Quién la sube se toma de
    form.uploader (lo pone la vista). Cada validación queda registrada en PhotoCheck (así
    se cuentan las llamadas del mes); al guardar el equipo o jugador se le añade la foto.
    Una foto rechazada no se guarda. Con form.check_only (la comprobación de nombres
    parecidos que hace el formulario antes de enviarse) no se procesa ni se valida.
    """
    from .models import PhotoCheck
    from .moderation import moderate

    photo = form.cleaned_data.get(field_name)
    # Solo los ficheros recién subidos traen content_type; una foto ya guardada se deja igual.
    if not (photo and hasattr(photo, "content_type")) or getattr(form, "check_only", False):
        return photo
    started = time.monotonic()
    content = process_image(photo)
    processed = time.monotonic()
    result = moderate(content)
    moderated = time.monotonic()
    uploader = getattr(form, "uploader", None)
    check = PhotoCheck.objects.create(
        club=getattr(form.instance, "club", None) or getattr(form, "club", None),
        uploaded_by=uploader if uploader and uploader.is_authenticated else None,
        status=result.status, reason=result.reason, api_called=result.api_called,
    )
    if moderated - started > SLOW_PHOTO_SECONDS:
        logger.warning("Foto lenta: %.2f s en total (procesar %.2f s, validar %.2f s, %s bytes subidos)",
                       moderated - started, processed - started, moderated - processed, getattr(photo, "size", "?"))
    if result.status == PhotoCheck.REJECTED:
        raise ValidationError(_("La foto no se puede usar: parece contener contenido no permitido. Elige otra."))
    form.instance._photo_check_id = check.pk
    return content


def _is_used(model, field_name, name, exclude_pk=None):
    """True si alguna fila de ``model`` (salvo ``exclude_pk``) sigue usando el fichero ``name``."""
    return model._default_manager.filter(**{field_name: name}).exclude(pk=exclude_pk).exists()


def _delete_later(storage, model, field_name, name):
    """Borra el fichero tras confirmar la transacción, si es nuestro y nadie más lo usa."""
    if not name or not name.startswith(tuple(f"{d}/" for d in PHOTO_DIRS)):
        return

    def delete():
        """Borra el fichero si, ya confirmada la transacción, nadie lo usa."""
        if not _is_used(model, field_name, name):
            storage.delete(name)

    transaction.on_commit(delete)


def connect_photo_cleanup(model, field_name="photo"):
    """Conecta las señales que borran la foto antigua al cambiarla o al borrar el objeto."""
    from django.db.models.signals import post_delete, post_save, pre_save

    def on_pre_save(sender, instance, update_fields=None, **kwargs):
        """Al cambiar la foto, programa el borrado del fichero anterior."""
        if not instance.pk or (update_fields is not None and field_name not in update_fields):
            return
        old = sender._default_manager.filter(pk=instance.pk).values_list(field_name, flat=True).first()
        new = getattr(instance, field_name).name if getattr(instance, field_name) else None
        if old and old != new:
            _delete_later(getattr(instance, field_name).storage, sender, field_name, old)

    def on_post_delete(sender, instance, **kwargs):
        """Al borrar el objeto, programa el borrado de su foto."""
        file = getattr(instance, field_name)
        if file:
            _delete_later(file.storage, sender, field_name, file.name)

    def on_post_save(sender, instance, **kwargs):
        """
        Completa el registro de la validación de la foto recién subida (clean_photo_field)
        con la ruta guardada, el club y el equipo o jugador.
        """
        check_id = instance.__dict__.pop("_photo_check_id", None)
        file = getattr(instance, field_name)
        if check_id and file:
            from .models import PhotoCheck

            PhotoCheck.objects.filter(pk=check_id).update(
                photo=file.name, club=getattr(instance, "club", None), **{sender._meta.model_name: instance},
            )

    post_save.connect(on_post_save, sender=model, weak=False, dispatch_uid=f"{model._meta.label}.{field_name}.post_save")
    pre_save.connect(on_pre_save, sender=model, weak=False, dispatch_uid=f"{model._meta.label}.{field_name}.pre_save")
    post_delete.connect(on_post_delete, sender=model, weak=False, dispatch_uid=f"{model._meta.label}.{field_name}.post_delete")
