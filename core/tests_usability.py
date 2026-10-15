"""
Tests de las mejoras de usabilidad del primer uso: registro por pasos con errores accesibles,
valores por defecto, portada con «Primeros pasos» primero, aviso de email por confirmar,
bienvenida de miembro, Club con accesos rápidos y estadísticas sin datos.
"""
import datetime

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Invitation, Membership
from core.services import create_club
from match.models import Match
from players.models import Player, SnpAccount
from team.models import Team

User = get_user_model()

CLUB = {"name": "Club Nuevo", "location": "Sevilla", "gender": "M", "country": "ES", "division": "500",
        "player-name": "Ana", "player-last_name": "Ruiz"}
SIGNUP = {"username": "nuevo", "email": "nuevo@example.com",
          "password1": "Clave-Segura-123", "password2": "Clave-Segura-123"}


class RegisterWizardTests(TestCase):
    """U1–U5: registro del club por pasos, valores por defecto, SNP preseleccionado y aviso a no capitanes."""

    def test_three_steps_for_a_new_account_and_two_for_google(self):
        page = self.client.get(reverse("register_club"))
        self.assertContains(page, "data-wizard")
        self.assertEqual(page.content.decode().count("data-wizard-step"), 3)
        self.assertContains(page, "register-wizard.js")
        self.assertContains(page, "data-wizard-summary")  # resumen «Faltan N campos»
        user = User.objects.create_user("g", email="g@example.com")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("register_club")).content.decode().count("data-wizard-step"), 2)

    def test_category_and_country_default_to_male_and_spain(self):
        form = self.client.get(reverse("register_club")).context["club_form"]
        self.assertEqual(form["gender"].value(), "M")
        self.assertEqual(form["country"].value(), "ES")
        self.assertFalse(form["division"].value())  # la división la elige el usuario

    def test_division_has_a_help_line_with_examples(self):
        self.assertContains(self.client.get(reverse("register_club")), "por ejemplo Future o 500")

    def test_snp_is_preselected_and_the_exact_match_notice_is_folded(self):
        page = self.client.get(reverse("register_club"))
        self.assertEqual(page.context["snp_form"]["mode"].value(), "snp")
        html = page.content.decode()
        self.assertRegex(html, r'<input type="radio" name="snp-mode" value="snp"[^>]*checked')
        self.assertContains(page, "<summary>Importante: debe coincidir con SNP</summary>")

    def test_empty_post_shows_errors_and_creates_nothing(self):
        response = self.client.post(reverse("register_club"), {"snp-mode": "manual"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Este campo es obligatorio.", count=None)
        self.assertFalse(User.objects.exists())

    def test_wizard_script_validates_before_each_step(self):
        from django.contrib.staticfiles import finders
        source = open(finders.find("js/register-wizard.js"), encoding="utf-8").read()
        for needle in ("ngettext('Falta %s campo'", "focusControl", "focusout", "Paso %s de %s", "sessionStorage"):
            self.assertIn(needle, source)
        # Nunca guarda contraseñas en el borrador.
        self.assertIn("el.type !== 'password'", source)

    def test_player_registration_page_warns_that_a_captain_must_invite(self):
        choose = self.client.get(reverse("register"))
        self.assertContains(choose, "Necesitas la invitación de tu capitán")
        page = self.client.get(reverse("register_account"))
        self.assertContains(page, "¿Eres capitán?")
        self.assertContains(page, f'href="{reverse("register_club")}"')


class FormErrorsAccessibilityTests(TestCase):
    """Los errores del formulario se enlazan con su campo y reciben el foco (form-errors.js, en todas las páginas)."""

    def test_script_is_loaded_everywhere_and_links_errors_to_fields(self):
        from django.contrib.staticfiles import finders
        self.assertContains(self.client.get(reverse("login")), "form-errors.js")
        source = open(finders.find("js/form-errors.js"), encoding="utf-8").read()
        for needle in ("aria-invalid", "aria-describedby", "focusControl", "window.ZyraForms"):
            self.assertIn(needle, source)

    def test_custom_select_announces_required_fields(self):
        from django.contrib.staticfiles import finders
        source = open(finders.find("js/custom-select.js"), encoding="utf-8").read()
        for needle in ("role', 'combobox'", "aria-expanded", "aria-activedescendant", "aria-required"):
            self.assertIn(needle, source)

    def test_scroll_padding_and_typing_hide_the_bottom_bar(self):
        from django.contrib.staticfiles import finders
        css = open(finders.find("style.css"), encoding="utf-8").read()
        self.assertIn("scroll-padding-top", css)
        self.assertIn(".z-typing .z-bottom-nav", css)
        self.assertIn("z-typing", open(finders.find("js/nav.js"), encoding="utf-8").read())


class HomeFirstStepsTests(TestCase):
    """U6, U8, U9: avisos y «Primeros pasos» primero, sin bloques vacíos."""

    def setUp(self):
        self.captain = User.objects.create_user("cap", "cap@example.com", "pass-12345")
        self.club = create_club("Club A", "Sevilla", self.captain, gender="M")
        self.client.force_login(self.captain)

    def test_first_steps_come_first_and_empty_blocks_are_hidden(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Prepara tu club en Zyra", html)
        for hidden in ("Todo al día", "Próximo enfrentamiento", "En racha", "Nadie encadena"):
            self.assertNotIn(hidden, html)
        self.assertIn("Siguiente paso", html)

    def test_empty_blocks_come_back_when_first_steps_are_dismissed(self):
        self.client.post(reverse("dismiss_onboarding"))
        html = self.client.get(reverse("home")).content.decode()
        for shown in ("Todo al día", "Próximo enfrentamiento", "En racha"):
            self.assertIn(shown, html)

    def test_next_step_order_is_players_invite_match(self):
        steps = self.client.get(reverse("home")).context["onboarding"]
        self.assertEqual([s["key"] for s in steps], ["players", "invite", "match"])
        self.assertEqual(self.client.get(reverse("home")).context["onboarding_next"]["key"], "players")

    def test_unconfirmed_email_shows_one_banner_with_resend_and_change(self):
        page = self.client.get(reverse("home"))
        self.assertContains(page, "Confirma tu email", count=1, html=False)
        self.assertContains(page, f'action="{reverse("resend_verification")}"')
        self.assertContains(page, f'href="{reverse("my_profile")}?edit=email"')

    def test_banner_disappears_when_the_email_is_verified(self):
        EmailAddress.objects.create(user=self.captain, email="cap@example.com", verified=True, primary=True)
        self.assertNotContains(self.client.get(reverse("home")), "Confirma tu email")

    def test_google_only_accounts_do_not_see_the_banner(self):
        google = User.objects.create_user("g", "g@example.com")  # sin contraseña
        Membership.objects.create(user=google, club=self.club, role=Membership.MEMBER)
        self.client.force_login(google)
        self.assertNotContains(self.client.get(reverse("home")), "Confirma tu email")

    def test_resend_from_home_returns_home_and_ignores_foreign_urls(self):
        response = self.client.post(reverse("resend_verification"), {"next": reverse("home")})
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        response = self.client.post(reverse("resend_verification"), {"next": "https://evil.example/"})
        self.assertRedirects(response, reverse("my_profile"), fetch_redirect_response=False)

    def test_member_empty_states_promise_what_they_will_see(self):
        member = User.objects.create_user("socio", password="pass-12345")
        Membership.objects.create(user=member, club=self.club, role=Membership.MEMBER)
        self.client.force_login(member)
        self.assertContains(self.client.get(reverse("home")), "Cuando tu capitán programe el próximo enfrentamiento")


class ProfileEmailLayoutTests(TestCase):
    """U7: el email ocupa toda la línea y los botones van debajo."""

    def test_buttons_are_in_a_row_below_the_email(self):
        user = User.objects.create_user("cap", "cap@example.com", "pass-12345")
        create_club("Club A", "Sevilla", user, gender="M")
        self.client.force_login(user)
        html = self.client.get(reverse("my_profile")).content.decode()
        self.assertLess(html.index("cap@example.com"), html.index("z-account-actions"))
        self.assertIn("Cambiar email", html)


class MemberWelcomeTests(TestCase):
    """Bienvenida de una pantalla tras aceptar una invitación."""

    def setUp(self):
        self.captain = User.objects.create_user("cap", "cap@example.com", "pass-12345", first_name="Eva", last_name="Sanz")
        self.club = create_club("Club A", "Sevilla", self.captain, gender="M")

    def join(self):
        member = User.objects.create_user("nuevo", "n@example.com", "pass-12345")
        invitation = Invitation.objects.create(club=self.club, created_by=self.captain)
        self.client.force_login(member)
        response = self.client.post(reverse("invitation", args=[invitation.token]))
        self.assertRedirects(response, reverse("member_welcome"), fetch_redirect_response=False)
        return member

    def test_welcome_shows_captain_team_and_empty_call_promise(self):
        self.join()
        page = self.client.get(reverse("member_welcome"))
        self.assertContains(page, "Ya formas parte de Club A")
        self.assertContains(page, "Eva Sanz")
        self.assertContains(page, "Tu próxima convocatoria")
        self.assertContains(page, "Cuando tu capitán programe un enfrentamiento")
        self.assertContains(page, reverse("my_player"))  # «Elegir mi jugador»

    def test_welcome_with_linked_player_goes_straight_home(self):
        member = self.join()
        Player.objects.create(club=self.club, name="Luis", last_name="Pérez", user=member)
        page = self.client.get(reverse("member_welcome"))
        self.assertContains(page, "Ir al inicio")
        self.assertNotContains(page, "Elegir mi jugador")

    def test_welcome_shows_the_next_match_and_call_status(self):
        member = self.join()
        Player.objects.create(club=self.club, name="Luis", last_name="Pérez", user=member)
        rival = Team.objects.create(club=self.club, name="Rival", in_group=True)
        Match.objects.create(club=self.club, local=self.club.own_team, visiting=rival,
                             start_date=datetime.date.today() + datetime.timedelta(days=3))
        page = self.client.get(reverse("member_welcome"))
        self.assertContains(page, "Rival")
        self.assertContains(page, "Todavía no hay convocatoria.")

    def test_anonymous_users_cannot_see_it(self):
        self.assertNotEqual(self.client.get(reverse("member_welcome")).status_code, 200)


class ClubHubTests(TestCase):
    """Ficha del club con estado y enlace directo, accesos rápidos y zona de peligro."""

    def setUp(self):
        self.captain = User.objects.create_user("cap", "cap@example.com", "pass-12345")
        self.club = create_club("Club A", "Sevilla", self.captain, gender="M")
        self.client.force_login(self.captain)

    def test_todo_chips_link_to_what_is_missing(self):
        page = self.client.get(reverse("club_home"))
        for text in ("Conectar ahora", "Invita a tu primer jugador", "Añade tu primer rival"):
            self.assertContains(page, text)

    def test_snp_chip_turns_into_connected(self):
        account = SnpAccount(club=self.club)
        account.username, account.password = "cap", "secreto"
        account.save()
        page = self.client.get(reverse("club_home"))
        self.assertContains(page, "Conectada")
        self.assertNotContains(page, "Conectar ahora")

    def test_quick_actions_are_two_taps_from_home(self):
        page = self.client.get(reverse("club_home"))
        for name in ("create_team", "create_player", "create_match"):
            self.assertContains(page, f'href="{reverse(name)}"')
        self.assertContains(page, reverse("club_members") + "#invitaciones")

    def test_leave_club_sits_in_a_separate_danger_zone(self):
        html = self.client.get(reverse("club_home")).content.decode()
        self.assertIn("Zona de peligro", html)
        self.assertLess(html.index("Zona de peligro"), html.index("leaveClubModal"))

    def test_members_page_has_a_one_line_intro_and_folded_details(self):
        html = self.client.get(reverse("club_members")).content.decode()
        self.assertIn("Invita por email o comparte un enlace. Caduca a las 24 horas.", html)
        self.assertIn("<summary>Más información</summary>", html)

    def test_club_legend_explains_club_team_and_group(self):
        self.assertContains(self.client.get(reverse("club_home")), "Tu club reúne a los miembros")


class EmptyStatesTests(TestCase):
    """Estados vacíos con acción: rivales, crear enfrentamiento y estadísticas sin cerrar ninguno."""

    def setUp(self):
        self.captain = User.objects.create_user("cap", "cap@example.com", "pass-12345")
        self.club = create_club("Club A", "Sevilla", self.captain, gender="M")
        self.client.force_login(self.captain)

    def test_rivals_empty_state_offers_create_rival(self):
        page = self.client.get(reverse("list_teams"))
        self.assertContains(page, "Añade a tu primer rival")
        self.assertContains(page, f'href="{reverse("create_team")}"')

    def test_create_match_links_to_create_rival_when_there_are_none(self):
        page = self.client.get(reverse("create_match"))
        self.assertContains(page, "Todavía no tienes rivales en tu grupo.")
        Team.objects.create(club=self.club, name="Rival", in_group=True)
        self.assertNotContains(self.client.get(reverse("create_match")), "Todavía no tienes rivales en tu grupo.")

    def test_create_match_has_a_single_type_selector(self):
        page = self.client.get(reverse("create_match"))
        self.assertContains(page, "data-kind-select")
        self.assertContains(page, '<option value="amistoso">Amistoso</option>')
        self.assertContains(page, "Tipo de enfrentamiento")

    def test_stats_without_closed_matches_are_one_card_without_tabs_or_filters(self):
        for name in ("team_statistics", "player_statistics", "pair_statistics"):
            page = self.client.get(reverse(name))
            self.assertTemplateUsed(page, "stats_empty.html")
            self.assertContains(page, "Cierra tu primer enfrentamiento y verás esto")
            self.assertNotContains(page, "st-tabs")
            self.assertNotContains(page, "st-seasons")

    def test_stats_come_back_with_a_closed_match(self):
        rival = Team.objects.create(club=self.club, name="Rival", in_group=True)
        Match.objects.create(club=self.club, local=self.club.own_team, visiting=rival,
                             start_date=datetime.date(2026, 1, 10), draft_mode=False)
        page = self.client.get(reverse("team_statistics"))
        self.assertTemplateNotUsed(page, "stats_empty.html")
        self.assertContains(page, "st-tabs")

    def test_members_see_a_promise_instead_of_a_button(self):
        member = User.objects.create_user("socio", password="pass-12345")
        Membership.objects.create(user=member, club=self.club, role=Membership.MEMBER)
        self.client.force_login(member)
        page = self.client.get(reverse("team_statistics"))
        self.assertContains(page, "Cuando tu capitán cierre el primer enfrentamiento")
        self.assertNotContains(page, reverse("create_match"))

    def test_players_list_empty_state_has_an_action_for_the_captain(self):
        Player.objects.filter(club=self.club).delete()
        page = self.client.get(reverse("list_players"))
        self.assertContains(page, "Añade a tu primer jugador")
