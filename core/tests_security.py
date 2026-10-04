"""
Pruebas de la revisión de seguridad (informe en informes/revision-seguridad.md del
proyecto): permisos por URL, página «Sin permiso», validación de formularios y
contenido escrito por usuarios que acaba en HTML, JavaScript o PDF.
"""
import datetime

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from call.models import Call
from core.models import Invitation, Membership
from core.services import create_club
from match.models import Game, Match
from match.notifications import report_filename
from match.report import build_report
from match.report_pdf import render_report
from players.models import Player, SnpTeamImport
from team.models import Team

User = get_user_model()
PASSWORD = "pass-12345-x"


class SecurityBase(TestCase):
    def setUp(self):
        cache.clear()
        self.captain = User.objects.create_user("captain", password=PASSWORD, email="captain@example.com")
        self.member = User.objects.create_user("member", password=PASSWORD, email="member@example.com")
        self.club = create_club("Club A", "Sevilla", self.captain)
        self.membership = Membership.objects.create(user=self.member, club=self.club, role=Membership.MEMBER)
        self.captain_membership = Membership.objects.get(user=self.captain, club=self.club)
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.player = Player.objects.create(club=self.club, name="Ana", last_name="Alpha")
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                          start_date=datetime.date(2025, 10, 1))
        self.call = Call.objects.create(match=self.match)
        self.game = Game.objects.create(match=self.match, n_game=1)


class CaptainOnlyUrlsTests(SecurityBase):
    """Un miembro que escribe en la barra de direcciones una URL de capitán ve «Sin permiso»."""

    def captain_urls(self):
        m, c, g = self.match.public_id, self.call.public_id, self.game.public_id
        invitation = Invitation.objects.create(club=self.club, created_by=self.captain)
        team_import = SnpTeamImport.objects.create(club=self.club, started_by=self.captain)
        return [
            reverse("create_match"), reverse("delete_match", args=[m]), reverse("create_call", args=[m]),
            reverse("close_call", args=[m]), reverse("resend_call_report", args=[m]),
            reverse("call_report", args=[m]), reverse("edit_call", args=[c]), reverse("closed_call", args=[c]),
            reverse("existing_call", args=[m]), reverse("create_game", args=[m]),
            reverse("create_result", args=[g]), reverse("edit_result", args=[g]),
            reverse("close_match", args=[m]), reverse("edit_games_match", args=[m]),
            reverse("delete_call", args=[m]), reverse("create_penalty", args=[c]),
            reverse("create_player"), reverse("edit_player", args=[self.player.public_id]),
            reverse("delete_player", args=[self.player.public_id]), reverse("manage_roster"),
            reverse("unlink_player", args=[self.player.public_id]),
            reverse("snp_account"), reverse("snp_account_delete"), reverse("complete_team_start"),
            reverse("complete_team_status", args=[team_import.public_id]),
            reverse("complete_team_confirm", args=[team_import.public_id]),
            reverse("complete_team_cancel", args=[team_import.public_id]),
            reverse("create_team"), reverse("edit_team", args=[self.rival.public_id]),
            reverse("warnings_statistics"), reverse("club_members"),
            reverse("update_member", args=[self.membership.public_id]),
            reverse("remove_member", args=[self.membership.public_id]),
            reverse("create_invitation"), reverse("create_invitation_link"),
            reverse("revoke_invitation", args=[invitation.public_id]),
        ]

    def test_member_gets_forbidden_page_on_every_captain_url(self):
        self.client.login(username="member", password=PASSWORD)
        for url in self.captain_urls():
            for method in ("get", "post"):
                with self.subTest(url=url, method=method):
                    response = getattr(self.client, method)(url)
                    self.assertEqual(response.status_code, 403)
                    self.assertTemplateUsed(response, "403.html")
        # Nada ha cambiado
        self.assertTrue(Membership.objects.filter(pk=self.membership.pk).exists())
        self.assertTrue(Match.objects.filter(pk=self.match.pk, draft_mode=True).exists())
        self.assertTrue(Player.objects.filter(pk=self.player.pk).exists())

    def test_anonymous_is_sent_to_login(self):
        for url in self.captain_urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)

    def test_forbidden_page_in_both_languages(self):
        self.client.login(username="member", password=PASSWORD)
        response = self.client.get(reverse("club_members"))
        self.assertContains(response, "Sin permiso", status_code=403)
        self.assertContains(response, "Solo los capitanes del club", status_code=403)

        self.client.cookies["django_language"] = "en"
        response = self.client.get(reverse("club_members"))
        self.assertContains(response, "Access denied", status_code=403)
        self.assertContains(response, "Only club captains", status_code=403)

    def test_member_does_not_see_penalty_form(self):
        self.client.login(username="member", password=PASSWORD)
        response = self.client.get(reverse("view_call_log", args=[self.call.public_id]))
        self.assertNotContains(response, reverse("create_penalty", args=[self.call.public_id]))
        self.client.login(username="captain", password=PASSWORD)
        response = self.client.get(reverse("view_call_log", args=[self.call.public_id]))
        self.assertContains(response, reverse("create_penalty", args=[self.call.public_id]))


class CsrfTests(SecurityBase):
    def test_form_without_csrf_token_shows_forbidden_page(self):
        client = Client(enforce_csrf_checks=True)
        client.login(username="captain", password=PASSWORD)
        response = client.post(reverse("create_invitation_link"))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "403.html")
        self.assertFalse(Invitation.objects.exists())


class StateChangesNeedPostTests(SecurityBase):
    def test_close_match_by_get_is_rejected(self):
        self.client.login(username="captain", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("close_match", args=[self.match.public_id])).status_code, 405)
        self.assertEqual(self.client.get(reverse("delete_call", args=[self.match.public_id])).status_code, 405)

    def test_call_of_confirmed_match_cannot_be_deleted(self):
        Match.objects.filter(pk=self.match.pk).update(draft_mode=False)
        self.client.login(username="captain", password=PASSWORD)
        self.client.post(reverse("delete_call", args=[self.match.public_id]))
        self.assertTrue(Call.objects.filter(pk=self.call.pk).exists())


class MemberEmailTests(SecurityBase):
    """Un capitán no puede cambiar el email de otro usuario (robo de cuenta con «Entrar con Google»)."""

    def setUp(self):
        super().setUp()
        self.client.login(username="captain", password=PASSWORD)

    def test_captain_cannot_change_other_member_email(self):
        self.client.post(reverse("update_member", args=[self.membership.public_id]),
                         {"email": "attacker@example.com", "role": Membership.MEMBER})
        self.member.refresh_from_db()
        self.assertEqual(self.member.email, "member@example.com")

    def test_role_still_changes_without_email(self):
        self.client.post(reverse("update_member", args=[self.membership.public_id]), {"role": Membership.ADMIN})
        self.membership.refresh_from_db()
        self.assertTrue(self.membership.is_admin)

    def test_own_email_can_change_but_must_be_unique(self):
        url = reverse("update_member", args=[self.captain_membership.public_id])
        self.client.post(url, {"email": "MEMBER@example.com", "role": Membership.ADMIN})
        self.captain.refresh_from_db()
        self.assertEqual(self.captain.email, "captain@example.com")

        EmailAddress.objects.create(user=self.captain, email="captain@example.com", verified=True, primary=True)
        self.client.post(url, {"email": "New@Example.com", "role": Membership.ADMIN})
        self.captain.refresh_from_db()
        self.assertEqual(self.captain.email, "new@example.com")
        # El email verificado anterior deja de valer para entrar con Google
        self.assertFalse(EmailAddress.objects.filter(user=self.captain, email="captain@example.com").exists())

    def test_members_page_only_shows_own_email_input(self):
        response = self.client.get(reverse("club_members"))
        self.assertContains(response, 'name="email" value="captain@example.com"')
        self.assertNotContains(response, 'name="email" value="member@example.com"')
        self.assertContains(response, "member@example.com")


class SwitchClubTests(SecurityBase):
    def test_non_numeric_club_id_is_404_not_500(self):
        self.client.login(username="captain", password=PASSWORD)
        self.assertEqual(self.client.post(reverse("switch_club"), {"club_id": "1 OR 1=1"}).status_code, 404)
        self.assertEqual(self.client.post(reverse("switch_club"), {}).status_code, 404)


class StoredXssTests(SecurityBase):
    def test_player_name_cannot_inject_script_in_team_statistics(self):
        Player.objects.filter(pk=self.player.pk).update(name="</script><script>alert(1)</script>")
        self.client.login(username="member", password=PASSWORD)
        response = self.client.get(reverse("team_statistics"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>alert(1)")
        self.assertContains(response, 'id="column-chart-data"')


class FormValidationTests(SecurityBase):
    def setUp(self):
        super().setUp()
        self.client.login(username="captain", password=PASSWORD)

    def edit(self, **data):
        values = {"name": "Ana", "last_name": "Alpha", "position": "Derecha", "skillfull_hand": "Diestro",
                  "joined_season": "2024-2025", "in_team": "on", **data}
        return self.client.post(reverse("edit_player", args=[self.player.public_id]), values)

    def test_edit_player_saves_valid_data(self):
        response = self.edit(name="Ángela", position="Revés")
        self.assertRedirects(response, reverse("list_players"), fetch_redirect_response=False)
        self.player.refresh_from_db()
        self.assertEqual((self.player.name, self.player.position), ("Ángela", "Revés"))

    def test_edit_player_rejects_invalid_values(self):
        cases = {
            "position": {"position": "Portero"},
            "hand": {"skillfull_hand": "<script>"},
            "season": {"joined_season": "'; DROP TABLE"},
            "long name": {"name": "A" * 101},
            "html name": {"name": "<img src=x onerror=alert(1)>"},
            "empty name": {"name": ""},
            "missing position": {"position": ""},
        }
        for label, data in cases.items():
            with self.subTest(label):
                response = self.edit(**data)
                self.assertEqual(response.status_code, 200)
                self.player.refresh_from_db()
                self.assertEqual((self.player.name, self.player.position, self.player.joined_season),
                                 ("Ana", "NONE", self.player.joined_season))

    def test_create_player_and_team_reject_html(self):
        self.client.post(reverse("create_player"), {
            "name": "<b>Eva", "last_name": "X", "position": "Derecha", "skillfull_hand": "Diestro", "confirm": "1"})
        self.assertFalse(Player.objects.filter(name__contains="<").exists())
        self.client.post(reverse("create_team"), {
            "name": "Equipo\nmalo", "location": "Sevilla", "gender": "M", "country": "ES", "division": "500",
            "confirm": "1"})
        self.assertFalse(Team.objects.filter(name__contains="malo").exists())

    def test_register_club_rejects_html_name(self):
        self.client.logout()
        self.client.post(reverse("register_club"), {
            "name": "<script>x</script>", "location": "Cádiz", "gender": "F", "country": "ES", "division": "500",
            "username": "nuevo", "email": "n@example.com", "password1": "Clave-Segura-123",
            "password2": "Clave-Segura-123", "player-name": "Ana", "player-last_name": "Ruiz",
        })
        self.assertFalse(User.objects.filter(username="nuevo").exists())


class ReportPdfTests(SecurityBase):
    def test_pdf_survives_markup_in_names(self):
        Team.objects.filter(pk=self.rival.pk).update(name='Rival <b> & "Co"; x')
        names = ["<b>Ana", "Bea & Co", "</para>", "Lu<font", "Eva", "Iris", "Olga", "Rita", "Sara", "Tere"]
        players = [Player.objects.create(club=self.club, name=n, last_name="X", snp_score=10) for n in names]
        self.call.players.set(players)
        self.match.refresh_from_db()
        pdf = render_report(build_report(self.call))
        self.assertTrue(pdf.startswith(b"%PDF"))

        filename = report_filename(self.match)
        self.assertNotIn('"', filename)
        self.assertNotIn(";", filename)
        self.assertTrue(filename.endswith(".pdf"))


class LoginThrottleTests(SecurityBase):
    def login(self, password):
        return self.client.post(reverse("login"), {"username": "member", "password": password})

    def test_locks_after_repeated_failures(self):
        for _ in range(5):
            self.assertEqual(self.login("wrong").status_code, 200)
        response = self.login(PASSWORD)
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Demasiados intentos", status_code=429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_success_resets_the_counter(self):
        for _ in range(4):
            self.login("wrong")
        self.assertEqual(self.login(PASSWORD).status_code, 302)
        self.client.logout()
        for _ in range(4):
            self.login("wrong")
        self.assertEqual(self.login(PASSWORD).status_code, 302)
