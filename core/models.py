"""
Modelos base de la aplicación multi-club: clubes, membresías, invitaciones y los
registros de moderación (validación de fotos, fotos eliminadas y emails bloqueados).
"""
import datetime
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .public_id import PublicIdModel


class Club(PublicIdModel):
    """
    Cada club es un "inquilino" de la aplicación: tiene sus propios jugadores,
    equipos rivales, partidos, convocatorias y estadísticas.
    Ningún usuario puede ver datos de un club al que no pertenece.
    """
    PUBLIC_ID_PREFIX = "CLB"
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Club suspendido por el personal de Zyra (back-office): sus miembros no pueden entrar
    # hasta que se reactive. No se borra nada.
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.CharField(max_length=500, blank=True)
    # El capitán cerró la lista de «Primeros pasos» de la portada (core.onboarding). Los
    # clubes que ya existían cuando se añadió la lista la tienen cerrada.
    onboarding_dismissed_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_suspended(self):
        """True si el personal ha suspendido el club."""
        return self.suspended_at is not None

    def save(self, *args, **kwargs):
        """Genera un slug único a partir del nombre (añadiendo -2, -3...) si no tiene."""
        if not self.slug:
            base = slugify(self.name) or "club"
            slug, n = base, 2
            while Club.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def own_team(self):
        """Equipo (Team) que representa al propio club en los enfrentamientos."""
        return self.teams.filter(is_own=True).first()

    def __str__(self):
        """Nombre del club."""
        return self.name


class Membership(PublicIdModel):
    """
    Pertenencia de un usuario a un club con su rol: capitán (puede gestionar el club)
    o miembro (solo lectura). Un usuario solo puede tener una membresía por club.
    """
    PUBLIC_ID_PREFIX = "MBR"
    ADMIN = "admin"
    MEMBER = "member"
    ROLES = [
        (ADMIN, _("Capitán")),
        (MEMBER, _("Miembro (solo lectura)")),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=ROLES, default=MEMBER)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "club"], name="unique_membership_user_club"),
        ]

    @property
    def is_admin(self):
        """True si el miembro es capitán del club."""
        return self.role == self.ADMIN

    def __str__(self):
        """Usuario, club y rol."""
        return f"{self.user} - {self.club} ({self.get_role_display()})"


INVITATION_TTL = datetime.timedelta(hours=24)


def _invitation_token():
    """Token aleatorio e imposible de adivinar para el enlace de invitación."""
    return secrets.token_urlsafe(24)


def _invitation_expiry():
    """Fecha de caducidad por defecto de una invitación (ahora + INVITATION_TTL)."""
    return timezone.now() + INVITATION_TTL


class InvitationQuerySet(models.QuerySet):
    """QuerySet de Invitation con filtros propios."""
    def pending(self):
        """
        Invitaciones que todavía se pueden aceptar: sin caducar y, si son de un solo uso
        (las de email), sin usar. Los enlaces compartidos sirven para varias personas.
        """
        return self.filter(models.Q(used_at__isnull=True) | models.Q(reusable=True), expires_at__gt=timezone.now())


class Invitation(PublicIdModel):
    """
    Invitación al club como miembro: quien la abre se registra (o, si ya tiene cuenta,
    se une). La que el capitán envía por email es de un solo uso; el enlace que genera
    para compartirlo (``reusable``) lo pueden usar varias personas. Caducan a las 24 h.
    """
    PUBLIC_ID_PREFIX = "INV"
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="invitations")
    token = models.CharField(max_length=64, unique=True, default=_invitation_token, editable=False)
    # Email al que se envió. Vacío en las invitaciones antiguas, que se compartían como enlace.
    email = models.EmailField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="invitations_sent",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_invitation_expiry)
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="invitations_used",
    )
    # En los enlaces compartidos, used_by y used_at son los del último que se unió.
    used_at = models.DateTimeField(null=True, blank=True)
    # Enlace compartido: sirve para varias personas hasta que caduca o se anula.
    reusable = models.BooleanField(default=False)
    # Cuántas personas se han unido con esta invitación.
    use_count = models.PositiveIntegerField(default=0)

    objects = InvitationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_used(self):
        """True si es de un solo uso y ya se ha aceptado (un enlace compartido nunca se agota)."""
        return not self.reusable and self.used_at is not None

    @property
    def is_expired(self):
        """True si ya ha pasado la fecha de caducidad."""
        return timezone.now() >= self.expires_at

    @property
    def is_valid(self):
        """La invitación todavía se puede aceptar: ni usada ni caducada."""
        return not self.is_used and not self.is_expired

    def __str__(self):
        """Club y comienzo del token."""
        return f"Invitación a {self.club} ({self.token[:6]}…)"


class PhotoCheckQuerySet(models.QuerySet):
    """QuerySet de PhotoCheck con filtros propios."""
    def for_user(self, user):
        """Fotos guardadas que ha subido ``user`` o que son de su jugador."""
        return self.filter(models.Q(uploaded_by=user) | models.Q(player__user=user)).exclude(photo="")


class PhotoCheck(PublicIdModel):
    """
    Resultado de validar una foto subida (escudo o foto de jugador) con AWS Rekognition
    (core/moderation.py). Las rechazadas no se guardan; las que no se han podido validar
    (sin configurar, fuera del plan gratuito, error) se guardan y el personal las revisa
    en el back-office: si es correcta pasa a «Validada», igual que si la hubiera aprobado
    Rekognition (``api_called`` dice cuál de los dos la validó).
    """
    PUBLIC_ID_PREFIX = "PHC"
    APPROVED = "approved"
    REJECTED = "rejected"
    UNCHECKED = "unchecked"
    STATUSES = [
        (APPROVED, _("Validada")),
        (REJECTED, _("Rechazada")),
        (UNCHECKED, _("Pendiente de revisar")),
    ]

    club = models.ForeignKey(Club, on_delete=models.SET_NULL, null=True, blank=True, related_name="photo_checks")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="photo_checks",
    )
    team = models.ForeignKey("team.Team", on_delete=models.SET_NULL, null=True, blank=True, related_name="photo_checks")
    player = models.ForeignKey("players.Player", on_delete=models.SET_NULL, null=True, blank=True, related_name="photo_checks")
    # Ruta en el almacenamiento (vacía en las rechazadas, que no se guardan).
    photo = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES)
    # Motivo: etiquetas de Rekognition que la rechazaron o por qué no se validó.
    reason = models.CharField(max_length=500, blank=True)
    # True si se llamó a Rekognition (cuenta para el límite mensual gratuito).
    api_called = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PhotoCheckQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]

    @property
    def subject(self):
        """Jugador o equipo al que pertenece la foto (None si ya no existe)."""
        return self.player or self.team

    @property
    def subject_label(self):
        """Texto para mostrar de quién es la foto: «Foto de ...» o «Escudo de ...»."""
        from django.utils.translation import gettext

        if self.player:
            return gettext("Foto de %(player)s") % {"player": self.player.full_name}
        if self.team:
            return gettext("Escudo de %(team)s") % {"team": self.team.name}
        return gettext("Foto")

    @property
    def owner(self):
        """
        Responsable de la foto (se le avisa y cuenta para él si se elimina): quien la subió;
        si no se sabe (fotos anteriores a la revisión), el jugador enlazado o un capitán del club.
        """
        if self.uploaded_by:
            return self.uploaded_by
        if self.player and self.player.user:
            return self.player.user
        if self.club:
            captain = self.club.memberships.filter(role=Membership.ADMIN).select_related("user").order_by("id").first()
            return captain.user if captain else None
        return None

    @property
    def in_use(self):
        """La foto sigue siendo la del equipo o jugador."""
        subject = self.subject
        return bool(self.photo and subject and subject.photo and subject.photo.name == self.photo)

    def __str__(self):
        """Estado y ruta de la foto."""
        return f"{self.get_status_display()}: {self.photo or '—'}"


class PhotoRemoval(PublicIdModel):
    """
    Foto eliminada por el personal desde el back-office por no cumplir los términos y
    condiciones. Se avisa por email al jugador (o a quien subió el escudo); las veces
    que le ha pasado a un usuario se muestran al personal, que puede suspender su cuenta
    y eliminar el equipo si se repite.
    """
    PUBLIC_ID_PREFIX = "PHR"
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="photo_removals",
    )
    club = models.ForeignKey(Club, on_delete=models.SET_NULL, null=True, blank=True, related_name="photo_removals")
    # De quién era la foto: «Jugador ANA RUIZ» o «Escudo de CD Tomares».
    subject = models.CharField(max_length=200)
    reason = models.CharField(max_length=500, blank=True)
    removed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    email_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        """De quién era la foto y la fecha en que se eliminó."""
        return f"{self.subject} ({self.created_at:%d/%m/%Y})"


class BlockedEmail(PublicIdModel):
    """
    Email bloqueado por el personal (al suspender un club o a mano en el back-office):
    no puede crear cuentas ni clubes, ni recibir o aceptar invitaciones. Se guarda
    normalizado (core.blocklist.normalize_email) en un campo único, así comprobar un email
    es una búsqueda por índice aunque la lista crezca mucho.
    """
    PUBLIC_ID_PREFIX = "BLE"
    email = models.CharField(max_length=254, unique=True)
    # Tal y como estaba escrito (para mostrarlo); la comprobación usa `email`.
    original_email = models.EmailField(max_length=254)
    # Cuenta que tenía el email al bloquearlo: sigue bloqueada aunque cambie de email.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="blocked_emails",
    )
    club = models.ForeignKey(Club, on_delete=models.SET_NULL, null=True, blank=True, related_name="blocked_emails")
    reason = models.CharField(max_length=500, blank=True)
    blocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        """El email tal y como se escribió."""
        return self.original_email
