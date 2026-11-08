"""
Enlace de disponibilidad de un enfrentamiento: el capitán lo comparte (por WhatsApp, por ejemplo) y
cada jugador de la plantilla responde Sí, No o Pendiente. Es solo disponibilidad: la alineación la
hacen el capitán o los gestores, y los «Sí» alimentan el selector de la convocatoria.

Aquí vive la lógica (enlace, texto prefabricado, respuestas, resumen para el capitán y recordatorio);
las vistas están en ``call/views.py``.
"""
import logging
import math
import time

from django.conf import settings
from django.core.cache import cache
from django.core.mail import get_connection
from django.db.models import Q
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.html import escape
from django.utils.translation import gettext as _
from urllib.parse import quote

from core import ratelimit
from core.competitions import competition_for
from core.emails import build_email
from players.models import Player

from .models import Availability, Call

logger = logging.getLogger(__name__)

# Entre dos recordatorios manuales del mismo enfrentamiento tiene que pasar este tiempo.
REMINDER_COOLDOWN_SECONDS = 60 * 60
# Tope de recordatorios al día por club (suma de todos sus enfrentamientos): protege la cuenta que envía los correos.
REMINDERS_PER_CLUB_PER_DAY = 10

NO_ANSWER = "none"
BY_CAPTAIN = "captain"


def is_open(match):
    """True mientras se puede responder: el acta sigue abierta y la convocatoria no se ha cerrado."""
    call = Call.objects.filter(match=match).first()
    return bool(match.draft_mode and not (call and not call.draft_mode))


def link_path(match):
    """Ruta (sin dominio) del enlace de disponibilidad del enfrentamiento."""
    return reverse("availability", args=[match.availability_token])


def link_url(request, match):
    """
    Enlace de disponibilidad completo. Con ``SITE_URL`` configurado usa siempre el dominio oficial (los
    correos y el texto de WhatsApp no dependen de por dónde haya entrado quien los genera); sin él, el de la petición.
    """
    if settings.SITE_URL:
        return settings.SITE_URL + link_path(match)
    return request.build_absolute_uri(link_path(match))


def share_text(match, url):
    """
    Texto prefabricado para pegar en el grupo de WhatsApp: rival, competición, fase y jornada,
    fecha, hora y lugar (las líneas sin dato se omiten) y el enlace para responder.
    """
    lines = [_("Rival: %(rival)s") % {"rival": match.rival_label}]
    if match.match_type == match.AMISTOSO:
        lines.append(_("Amistoso"))
    else:
        lines.append(_("Competición: %(name)s") % {"name": competition_for(match).name})
        phase = match.get_match_type_display()
        if match.round_number:
            phase += " - " + _("Jornada %(n)s") % {"n": match.round_number}
        lines.append(_("Fase: %(phase)s") % {"phase": phase})
    lines.append("🗓️ " + _("Fecha: %(date)s") % {"date": date_format(match.start_date, format=_("l j \\d\\e F \\d\\e Y"))})
    if match.start_time:
        lines.append("⏰ " + _("Hora del partido: %(time)s") % {"time": f"{match.start_time:%H:%M}h"})
    if match.location:
        lines.append("📍 " + _("Lugar: %(place)s") % {"place": match.location})
    return "\n".join(lines) + "\n\n" + _("Responde aquí con tu disponibilidad:") + f"\n{url}"


def whatsapp_url(text):
    """Enlace de WhatsApp que abre el reparto de ``text``."""
    return "https://wa.me/?text=" + quote(text)


def regenerate_token(match):
    """Cambia el token del enlace: el anterior deja de funcionar."""
    from match.models import new_availability_token
    match.availability_token = new_availability_token()
    match.save(update_fields=["availability_token"])


def squad(match):
    """Jugadores que pueden responder: la plantilla del club (más quien ya respondió aunque haya salido)."""
    answered = Availability.objects.filter(match=match).values("player_id")
    return Player.objects.filter(club=match.club).filter(Q(in_team=True) | Q(id__in=answered))


def unanswered(players, matches):
    """
    Enfrentamientos de ``matches`` en los que alguno de ``players`` (sus fichas de un usuario, una por
    club) puede responder y aún no lo ha hecho: abiertos, de su club, con la convocatoria sin cerrar,
    sin respuesta suya y sin estar ya apuntado por el capitán. Devuelve ``(enfrentamiento, jugador)``.
    """
    by_club = {p.club_id: p for p in players if p.in_team}
    open_matches = [m for m in matches if m.club_id in by_club and m.draft_mode]
    if not open_matches:
        return []
    ids = [m.id for m in open_matches]
    answered = set(Availability.objects.filter(match_id__in=ids, player__in=by_club.values())
                   .values_list("match_id", "player_id"))
    called = set(Call.objects.filter(match_id__in=ids, players__in=by_club.values())
                 .values_list("match_id", "players"))
    closed = set(Call.objects.filter(match_id__in=ids, draft_mode=False).values_list("match_id", flat=True))
    return [(m, by_club[m.club_id]) for m in open_matches
            if m.id not in closed and (m.id, by_club[m.club_id].id) not in answered | called]


def valid_answer(answer):
    """True si ``answer`` es una de las respuestas posibles (Sí, No, Pendiente)."""
    return answer in dict(Availability.ANSWERS)


def set_answer(match, player, answer, comment=""):
    """
    Guarda la respuesta de ``player`` (la sustituye si ya había una). El comentario solo se
    conserva con «Pendiente» y se recorta a ``Availability.MAX_COMMENT``. Devuelve la fila, o ``None`` si
    la respuesta no es válida o ya no se puede responder.
    """
    if not valid_answer(answer) or not is_open(match):
        return None
    comment = " ".join((comment or "").split())[:Availability.MAX_COMMENT] if answer == Availability.MAYBE else ""
    row, _created = Availability.objects.update_or_create(
        match=match, player=player,
        defaults={"answer": answer, "comment": comment})
    return row


def answers_by_player(match):
    """``{player_id: Availability}`` de las respuestas del enfrentamiento."""
    return {a.player_id: a for a in Availability.objects.filter(match=match)}


def board(match):
    """
    Resumen para el capitán o los gestores: ``{"rows", "counts"}``. Cada fila lleva el jugador
    (``player``), su estado (``state``: «yes», «no», «maybe», «captain» si el capitán lo apuntó
    sin respuesta, o «none»), y el comentario. ``counts`` cuenta cada estado y
    ``groups`` agrupa las filas en Sí, No, Pendiente y Sin respuesta (con los apuntados por el capitán) y
    ``tags`` da esos mismos cuatro contadores, en el mismo orden, para la tarjeta de la ficha.
    """
    answers = answers_by_player(match)
    call = Call.objects.filter(match=match).first()
    called = set(call.players.values_list("id", flat=True)) if call else set()
    rows = []
    for player in squad(match).order_by("name", "last_name"):
        answer = answers.get(player.id)
        if answer:
            state = answer.answer
        elif player.id in called:
            state = BY_CAPTAIN
        else:
            state = NO_ANSWER
        rows.append({"player": player, "state": state, "comment": answer.comment if answer else "",
                     "called": player.id in called})
    order = {Availability.YES: 0, Availability.MAYBE: 1, Availability.NO: 2, BY_CAPTAIN: 3, NO_ANSWER: 4}
    rows.sort(key=lambda r: order[r["state"]])
    counts = {key: sum(1 for r in rows if r["state"] == key) for key in order}
    # Listado de la ventana «Ver respuestas»: Sí, No, Pendiente y Sin respuesta (con los apuntados por el capitán).
    groups = [
        {"key": Availability.YES, "label": _("Sí"), "rows": [r for r in rows if r["state"] == Availability.YES]},
        {"key": Availability.NO, "label": _("No"), "rows": [r for r in rows if r["state"] == Availability.NO]},
        {"key": Availability.MAYBE, "label": _("Pendiente"),
         "rows": [r for r in rows if r["state"] == Availability.MAYBE]},
        {"key": NO_ANSWER, "label": _("Sin respuesta"),
         "rows": [r for r in rows if r["state"] in (NO_ANSWER, BY_CAPTAIN)]},
    ]
    tags = [{"key": g["key"], "label": g["label"], "n": len(g["rows"])} for g in groups]
    return {"rows": rows, "counts": counts, "groups": groups, "tags": tags}


def yes_player_ids(match):
    """Ids de los jugadores que han respondido «Sí» (preselección del selector de la convocatoria)."""
    return list(Availability.objects.filter(match=match, answer=Availability.YES).values_list("player_id", flat=True))


def availability_badges(match):
    """``{player_id: (respuesta, comentario)}`` para marcar a cada jugador en el selector de la convocatoria."""
    return {a.player_id: (a.answer, a.comment) for a in Availability.objects.filter(match=match)}


def pending_players(match):
    """
    Jugadores de la plantilla con cuenta y email que no han respondido ni están apuntados por el capitán
    y a quienes el capitán no ha silenciado los correos (``Player.emails_muted``).
    """
    answered = set(Availability.objects.filter(match=match).values_list("player_id", flat=True))
    call = Call.objects.filter(match=match).first()
    called = set(call.players.values_list("id", flat=True)) if call else set()
    return [p for p in squad(match).select_related("user").order_by("name", "last_name")
            if p.user_id and p.user.is_active and p.user.email and not p.emails_muted
            and p.id not in answered | called]


def reminder_key(match):
    """Clave de caché del enfriamiento del recordatorio de ``match``."""
    return f"availability-reminder:{match.pk}"


def reminder_minutes_left(match):
    """Minutos que faltan para poder enviar otro recordatorio de ``match`` (0 si ya se puede)."""
    try:
        sent_at = cache.get(reminder_key(match))
    except Exception:
        logger.exception("Caché no disponible al leer la espera del recordatorio")
        return 1
    if not sent_at:
        return 0
    left = sent_at + REMINDER_COOLDOWN_SECONDS - time.time()
    return max(math.ceil(left / 60), 1) if left > 0 else 0


def reminder_blocked(match):
    """True si ya se envió un recordatorio de este enfrentamiento hace menos de ``REMINDER_COOLDOWN_SECONDS``."""
    return reminder_minutes_left(match) > 0


def claim_reminder(match):
    """
    Reserva el recordatorio de ``match`` de forma atómica antes de enviar (dos peticiones a la vez no pasan las
    dos). Devuelve False si ya hay uno reciente o si la caché falla: aquí es mejor no enviar que enviar sin límite.
    """
    try:
        return bool(cache.add(reminder_key(match), time.time(), REMINDER_COOLDOWN_SECONDS))
    except Exception:
        logger.exception("Caché no disponible: no se envía el recordatorio")
        return False


def release_reminder(match):
    """Devuelve la reserva de ``claim_reminder`` (si no salió ningún correo, se puede reintentar enseguida)."""
    ratelimit.clear(reminder_key(match))


def club_over_daily_limit(club):
    """Cuenta un recordatorio del club y devuelve True si ya pasó de ``REMINDERS_PER_CLUB_PER_DAY`` hoy."""
    if not settings.RATE_LIMITS_ENABLED:
        return False
    return ratelimit.add_hit(f"availability-reminder-day:{club.pk}", 24 * 60 * 60) > REMINDERS_PER_CLUB_PER_DAY


def send_reminder(request, match):
    """
    Recordatorio manual del capitán: un correo con el enlace a cada jugador que aún no ha respondido.
    Devuelve cuántos salieron. Un fallo con un destinatario se anota y no corta a los demás. La espera entre
    recordatorios la reserva y la libera la vista (``claim_reminder`` / ``release_reminder``).
    """
    url = link_url(request, match)
    sent = 0
    connection = get_connection()
    for player in pending_players(match):
        subject = _("¿Puedes jugar? %(local)s – %(visiting)s") % {
            "local": match.local_name, "visiting": match.visiting_name}
        name = player.user.first_name or player.user.username
        when = f"{match.start_date:%d/%m/%Y}" + (f" {match.start_time:%H:%M}" if match.start_time else "")
        text = _("Hola %(name)s: el capitán te recuerda que falta tu respuesta para %(local)s – %(visiting)s "
                 "(%(when)s). Dile si puedes jugar aquí:\n%(url)s") % {
            "name": name, "local": match.local_name, "visiting": match.visiting_name, "when": when, "url": url}
        html = (f"<p>{escape(text.splitlines()[0])}</p>"
                f'<p><a href="{escape(url)}">{escape(_("Responder"))}</a></p>')
        try:
            email = build_email(subject, text, html, to=[player.user.email])
            email.connection = connection
            email.send()
            sent += 1
        except Exception:
            logger.exception("No se pudo enviar el recordatorio de disponibilidad a %s", player.user.email)
    return sent
