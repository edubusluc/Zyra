"""Registro de auditoría del back-office: quién hizo qué, sobre qué y cuándo."""
import logging

from core.ratelimit import client_ip

from .models import AuditLog

logger = logging.getLogger(__name__)

# Acciones registradas (clave -> texto para mostrar). Las claves son estables: no se renombran.
ACTIONS = {
    "club.suspend": "Club suspendido",
    "club.reactivate": "Club reactivado",
    "club.snp_unlimited": "Club sin límites en «Completar equipo»",
    "club.edit": "Club editado",
    "club.delete": "Club eliminado",
    "club.captain_transfer": "Capitanía traspasada",
    "club.crm": "Ficha CRM actualizada",
    "club.contact": "Correo al capitán",
    "user.deactivate": "Cuenta suspendida",
    "user.activate": "Cuenta reactivada",
    "user.password_reset": "Restablecimiento de contraseña enviado",
    "user.resend_confirmation": "Confirmación reenviada",
    "user.photos_delete": "Fotos del usuario eliminadas",
    "job.toggle": "Proceso activado o en pausa",
    "job.run": "Proceso lanzado a mano",
    "service.snp": "Servicio de SNP",
    "photo.approve": "Foto validada",
    "photo.delete": "Foto eliminada",
    "email.block": "Email bloqueado",
    "email.unblock": "Email desbloqueado",
    "account.warn": "Aviso a cuenta sin confirmar",
    "account.delete": "Cuenta sin confirmar eliminada",
    "sql.run": "Consulta SQL",
    "sql.export": "Consulta SQL exportada",
    "sql.save": "Consulta SQL guardada",
    "sql.delete": "Consulta SQL borrada",
    "import.confirm": "Importación hecha",
    "import.undo": "Importación deshecha",
    "impersonate.start": "Entrar como (inicio)",
    "impersonate.stop": "Entrar como (fin)",
    "task.create": "Tarea creada",
    "note.create": "Nota creada",
}


def audit(request, action, obj=None, label="", **detail):
    """
    Anota una acción del personal. ``request`` es la petición (o ``None`` desde un proceso);
    ``obj`` el objeto afectado (se guarda su tipo, su id público o numérico y su nombre) y
    ``detail`` datos libres (JSON). Nunca rompe la acción: si falla, solo se registra en el log.
    """
    try:
        user = getattr(request, "user", None)
        # Con «Entrar como» la persona responsable es siempre quien lo inició, nunca el usuario visto.
        user = getattr(request, "impersonator", None) or user
        if user is not None and not getattr(user, "is_authenticated", False):
            user = None
        AuditLog.objects.create(
            user=user, username=user.get_username() if user else "", action=action,
            object_type=obj._meta.model_name if obj is not None else "",
            object_id=str(getattr(obj, "public_id", None) or getattr(obj, "pk", "") or "") if obj is not None else "",
            object_label=(label or (str(obj) if obj is not None else ""))[:200],
            detail={k: v for k, v in detail.items() if v not in (None, "")},
            ip=(client_ip(request) or None) if request is not None and hasattr(request, "META") else None,
        )
    except Exception:  # la auditoría nunca debe impedir la acción
        logger.exception("No se ha podido anotar la acción %s en la auditoría", action)
