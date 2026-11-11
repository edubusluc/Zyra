"""Ayudas para los tests: un cliente que se comporta como el navegador con el campo oculto ``team``."""
from django.test import Client


class TeamClient(Client):
    """
    Cliente de test que, en cada POST, añade el campo ``team`` (id público del equipo activo de la sesión) si
    la petición no lo trae, igual que los formularios reales con su campo oculto. Para probar un envío sin el
    equipo o con otro distinto, basta pasar ``team`` a mano (también vacío).
    """

    def post(self, path, data=None, *args, **extra):
        """POST normal, con ``team`` rellenado desde el equipo activo cuando ``data`` es un diccionario sin él."""
        if (data is None or isinstance(data, dict)) and "team" not in (data or {}):
            public_id = self._active_team_id()
            if public_id:
                data = {**(data or {}), "team": public_id}
        return super().post(path, data, *args, **extra)

    def _active_team_id(self):
        """Id público del equipo activo del usuario con sesión (el de la sesión o el que elige el middleware), o None."""
        from core.middleware import SESSION_KEY, default_membership
        from core.models import Membership

        user_id = self.session.get("_auth_user_id") if self.cookies.get("sessionid") else None
        if not user_id:
            return None
        memberships = [m for m in Membership.objects.filter(user_id=user_id).select_related("club").order_by("club__name")
                       if not m.club.is_suspended and not m.club.is_archived]
        club_id = self.session.get(SESSION_KEY)
        membership = next((m for m in memberships if m.club_id == club_id), None) or default_membership(memberships)
        return str(membership.club.public_id) if membership else None
