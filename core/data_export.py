"""
Exportación de los datos personales de una cuenta (derecho de acceso y portabilidad, RGPD arts. 15 y 20).

``export_user_data`` devuelve un diccionario serializable a JSON con lo que Zyra guarda de la persona: cuenta,
preferencias, equipos y rol, fichas de jugador (actuales y anteriores) con su histórico de puntos SNP,
informes mensuales enviados y dispositivos de la app. No incluye secretos (contraseña, tokens) ni los datos de
otras personas del club: los partidos y las estadísticas son del club.
"""
from allauth.socialaccount.models import SocialAccount
from django.db.models import Q
from django.utils import timezone

from .models import Membership, MonthlyReportDelivery, UserPreference

EXPORT_LIMIT, EXPORT_WINDOW = 5, 60 * 60


def _iso(value):
    """Fecha o fecha y hora en ISO 8601 (``None`` si no hay)."""
    return value.isoformat() if value else None


def _sheet(player):
    """Una ficha de jugador con sus puntos SNP a lo largo del tiempo."""
    return {
        "club": player.club.name,
        "team": str(player.team),
        "name": player.name,
        "last_name": player.last_name,
        "position": player.position,
        "hand": player.skillfull_hand,
        "snp_score": player.snp_score,
        "in_team": player.in_team,
        "left_on": _iso(player.left_on),
        "joined_season": player.joined_season,
        "photo": player.photo.url if player.photo else None,
        "snp_history": [{"date": _iso(h.date), "season": h.season, "score": h.score} for h in player.snp_history.all()],
    }


def export_user_data(user):
    """Datos personales de ``user`` listos para volcar a JSON."""
    from api.models import DeviceToken
    from players.models import Player

    prefs = UserPreference.objects.filter(user=user).first()
    memberships = Membership.objects.filter(user=user).select_related("club").order_by("club__name")
    players = (Player.objects.filter(Q(user=user) | Q(past_user=user))
               .select_related("club", "team").prefetch_related("snp_history").order_by("club__name", "pk"))
    return {
        "generated_at": timezone.now().isoformat(),
        "note": ("Datos personales que Zyra guarda de tu cuenta. Los partidos, convocatorias y estadísticas del club "
                 "pertenecen al club y no se incluyen. Para cualquier otra petición, escribe a contacto@zyrapadel.com."),
        "account": {
            "username": user.get_username(),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "date_joined": _iso(user.date_joined),
            "last_login": _iso(user.last_login),
            "has_password": user.has_usable_password(),
            "google_linked": SocialAccount.objects.filter(user=user, provider="google").exists(),
        },
        "preferences": None if prefs is None else {
            "report_scope": prefs.report_scope,
            "monthly_report": prefs.monthly_report,
            "monthly_scope": prefs.monthly_scope,
            "match_result_email": prefs.match_result_email,
            "news_email": prefs.news_email,
            "match_stage_view": prefs.match_stage_view,
        },
        "memberships": [{"club": m.club.name, "role": m.role} for m in memberships],
        "player_sheets": [_sheet(p) for p in players],
        "monthly_reports": [{"month": _iso(d.month), "email": d.email, "sent_at": _iso(d.sent_at)}
                            for d in MonthlyReportDelivery.objects.filter(user=user).order_by("month")],
        "app_devices": [{"device_name": d.device_name, "created_at": _iso(d.created_at),
                         "last_used_at": _iso(d.last_used_at), "revoked_at": _iso(d.revoked_at)}
                        for d in DeviceToken.objects.filter(user=user)],
    }
