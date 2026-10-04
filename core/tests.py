import datetime
import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from call.models import Call
from core.models import Club, Membership
from core.services import create_club
from match.models import Match, Game
from players.models import Player
from team.models import Team

User = get_user_model()


class ClubIsolationTests(TestCase):
    """Cada club solo ve y gestiona sus propios datos."""

    def setUp(self):
        self.user_a = User.objects.create_user("admin_a", password="pass-a-12345")
        self.user_b = User.objects.create_user("admin_b", password="pass-b-12345")
        self.club_a = create_club("Club A", "Sevilla", self.user_a)
        self.club_b = create_club("Club B", "Madrid", self.user_b)

        self.player_a = Player.objects.create(club=self.club_a, name="Ana", last_name="Alpha")
        self.player_b = Player.objects.create(club=self.club_b, name="Bea", last_name="Beta")

        self.rival_a = Team.objects.create(club=self.club_a, name="Rival", location="X", in_group=True)
        self.rival_b = Team.objects.create(club=self.club_b, name="Rival", location="Y", in_group=True)

        self.match_a = Match.objects.create(
            club=self.club_a, local=self.club_a.own_team, visiting=self.rival_a,
            start_date=datetime.date(2025, 10, 1),
        )
        self.match_b = Match.objects.create(
            club=self.club_b, local=self.club_b.own_team, visiting=self.rival_b,
            start_date=datetime.date(2025, 10, 1),
        )

        self.client.login(username="admin_a", password="pass-a-12345")

    def test_create_club_sets_own_team_and_admin(self):
        self.assertEqual(self.club_a.own_team.name, "Club A")
        self.assertTrue(Membership.objects.get(user=self.user_a, club=self.club_a).is_admin)
        self.assertEqual(self.player_a.team, self.club_a.own_team)

    def test_lists_only_show_own_club_data(self):
        players = self.client.get(reverse("list_players")).context["players"]
        self.assertEqual([p.id for p in players], [self.player_a.id])

        teams = self.client.get(reverse("list_teams")).context["teams"]
        self.assertTrue(all(t.club_id == self.club_a.id for t in teams))

        matches = self.client.get(reverse("list_match"), {"season": "all"}).context["matches"]
        self.assertEqual([m.id for m in matches], [self.match_a.id])

    def test_foreign_objects_return_404(self):
        urls = [
            reverse("show_player", args=[self.player_b.public_id]),
            reverse("edit_player", args=[self.player_b.public_id]),
            reverse("edit_team", args=[self.rival_b.public_id]),
            reverse("call_for_match", args=[self.match_b.public_id]),
            reverse("create_call", args=[self.match_b.public_id]),
            reverse("delete_match", args=[self.match_b.public_id]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

        response = self.client.get(reverse("player_statistics"), {"player": self.player_b.public_id})
        self.assertEqual(response.status_code, 404)

    def test_foreign_match_urls_return_404(self):
        """Ninguna URL de partido, convocatoria o resultado de otro club es accesible cambiando el id."""
        call_b = Call.objects.create(match=self.match_b)
        game_b = Game.objects.create(match=self.match_b, n_game=1)
        urls = [
            reverse("call_for_match", args=[self.match_b.public_id]),
            reverse("create_call", args=[self.match_b.public_id]),
            reverse("existing_call", args=[self.match_b.public_id]),
            reverse("close_call", args=[self.match_b.public_id]),
            reverse("delete_call", args=[self.match_b.public_id]),
            reverse("create_game", args=[self.match_b.public_id]),
            reverse("edit_games_match", args=[self.match_b.public_id]),
            reverse("close_match", args=[self.match_b.public_id]),
            reverse("delete_match", args=[self.match_b.public_id]),
            reverse("call_report", args=[self.match_b.public_id]),
            reverse("edit_call", args=[call_b.public_id]),
            reverse("closed_call", args=[call_b.public_id]),
            reverse("create_penalty", args=[call_b.public_id]),
            reverse("create_result", args=[game_b.public_id]),
            reverse("edit_result", args=[game_b.public_id]),
        ]
        # Estas solo aceptan POST: un GET da 405 sea de quien sea el partido (no desvela nada).
        post_only = {reverse("delete_call", args=[self.match_b.public_id]),
                     reverse("close_match", args=[self.match_b.public_id])}
        for url in urls:
            for method in ("get", "post"):
                with self.subTest(url=url, method=method):
                    expected = 405 if method == "get" and url in post_only else 404
                    self.assertEqual(getattr(self.client, method)(url).status_code, expected)

        # Nada del otro club ha cambiado
        self.assertTrue(Match.objects.filter(pk=self.match_b.pk, draft_mode=True).exists())
        self.assertTrue(Call.objects.filter(pk=call_b.pk).exists())

    def test_member_of_both_clubs_only_sees_active_club_matches(self):
        """Aunque el usuario pertenezca a los dos clubes, solo accede a los partidos del club activo."""
        Membership.objects.create(user=self.user_a, club=self.club_b, role=Membership.MEMBER)
        self.assertEqual(self.client.get(reverse("call_for_match", args=[self.match_b.public_id])).status_code, 404)

        self.client.post(reverse("switch_club"), {"club_id": self.club_b.id})
        self.assertEqual(self.client.get(reverse("call_for_match", args=[self.match_b.public_id])).status_code, 200)
        self.assertEqual(self.client.get(reverse("call_for_match", args=[self.match_a.public_id])).status_code, 404)

    def test_player_statistics_only_link_own_club_matches(self):
        """La tabla de partidos del jugador no incluye enfrentamientos de otro club."""
        self.match_a.draft_mode = False
        self.match_a.save()
        Game.objects.create(match=self.match_a, n_game=1, score=3, winner="Local", draft_mode=False,
                            player_1_local=self.player_a, player_2_local=self.player_a)
        # Dato corrupto: el jugador de A aparece en un partido de B
        Game.objects.create(match=self.match_b, n_game=1, score=3, winner="Local", draft_mode=False,
                            player_1_local=self.player_a, player_2_local=self.player_b)

        response = self.client.get(reverse("player_statistics"), {"player": self.player_a.public_id, "season": "2025-2026"})
        self.assertEqual([g["match_id"] for g in response.context["d"]["games"]], [self.match_a.id])
        self.assertNotContains(response, reverse("call_for_match", args=[self.match_b.public_id]))

    def test_player_statistics_only_lists_own_players(self):
        response = self.client.get(reverse("player_statistics"))
        self.assertEqual(list(response.context["players"]), [self.player_a])

    def test_team_statistics_use_own_team(self):
        response = self.client.get(reverse("team_statistics"))
        self.assertEqual(response.context["team"], self.club_a.own_team)
        self.assertEqual([c["player"] for c in response.context["column_chart_data"]], ["ANA ALPHA"])

    def test_created_objects_belong_to_active_club(self):
        self.client.post(reverse("create_player"), {
            "name": "Nuevo", "last_name": "Jugador", "position": "NONE", "skillfull_hand": "NONE",
        })
        player = Player.objects.get(name="Nuevo")
        self.assertEqual(player.club, self.club_a)
        self.assertEqual(player.team, self.club_a.own_team)

        self.client.post(reverse("create_team"), {"name": "Otro equipo", "location": "Z", "gender": "M", "country": "ES", "division": "500"})
        self.assertEqual(Team.objects.get(name="Otro equipo").club, self.club_a)

    def test_identical_team_is_rejected(self):
        self.rival_a.gender, self.rival_a.country = "M", "ES"
        self.rival_a.save()
        data = {"name": "rival", "location": "Z", "gender": "M", "country": "ES", "division": "500", "confirm_similar": "1"}
        response = self.client.post(reverse("create_team"), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Team.objects.filter(club=self.club_a, name__iexact="rival").count(), 1)

    def test_cannot_create_match_with_foreign_teams(self):
        response = self.client.post(reverse("create_match"), {
            "local": self.club_a.own_team.id, "visiting": self.rival_b.id, "start_date": "2025-11-01",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Match.objects.filter(visiting=self.rival_b, club=self.club_a).exists())

    def test_match_requires_own_team(self):
        other = Team.objects.create(club=self.club_a, name="Otro", location="Z", in_group=True)
        self.client.post(reverse("create_match"), {
            "local": other.id, "visiting": self.rival_a.id, "start_date": "2025-11-01",
        })
        self.assertEqual(Match.objects.filter(club=self.club_a).count(), 1)

        self.client.post(reverse("create_match"), {
            "local": self.rival_a.id, "visiting": self.club_a.own_team.id, "start_date": "2025-11-01",
        })
        self.assertEqual(Match.objects.filter(club=self.club_a).count(), 2)

    def test_call_ignores_foreign_players(self):
        self.client.post(reverse("create_call", args=[self.match_a.public_id]), {
            "players": [self.player_a.id, self.player_b.id],
        })
        call = Call.objects.get(match=self.match_a)
        self.assertEqual(list(call.players.all()), [self.player_a])

    def test_create_games_uses_own_side(self):
        players = [Player.objects.create(club=self.club_a, name=f"P{i}", last_name="X") for i in range(10)]
        call = Call.objects.create(match=self.match_a, draft_mode=False)
        call.players.set(players)

        ordered = [{"player1Id": players[i].id, "player2Id": players[i + 1].id} for i in range(0, 10, 2)]
        import json
        self.client.post(reverse("create_game", args=[self.match_a.public_id]), {"ordered_games": json.dumps(ordered)})
        games = Game.objects.filter(match=self.match_a)
        self.assertEqual(games.count(), 5)
        self.assertTrue(all(g.player_1_local and g.player_1_visiting is None for g in games))


class RolesAndClubSwitchTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="pass-12345-x")
        self.viewer = User.objects.create_user("viewer", password="pass-12345-x")
        self.club = create_club("Club A", "Sevilla", self.owner)
        Membership.objects.create(user=self.viewer, club=self.club, role=Membership.MEMBER)

    def test_member_can_read_but_not_write(self):
        self.client.login(username="viewer", password="pass-12345-x")
        self.assertEqual(self.client.get(reverse("list_players")).status_code, 200)

        response = self.client.post(reverse("create_player"), {"name": "X", "last_name": "Y"})
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "403.html")
        self.assertFalse(Player.objects.exists())
        self.assertEqual(self.client.get(reverse("club_members")).status_code, 403)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("list_players"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_user_without_club(self):
        User.objects.create_user("lonely", password="pass-12345-x")
        self.client.login(username="lonely", password="pass-12345-x")
        self.assertRedirects(self.client.get(reverse("list_players")), reverse("no_club"))

    def test_switch_club(self):
        other = create_club("Club B", "Madrid", self.owner)
        Player.objects.create(club=other, name="Bea", last_name="Beta")
        self.client.login(username="owner", password="pass-12345-x")

        self.assertEqual(len(self.client.get(reverse("list_players")).context["players"]), 0)
        self.client.post(reverse("switch_club"), {"club_id": other.id})
        self.assertEqual(len(self.client.get(reverse("list_players")).context["players"]), 1)

    def test_cannot_switch_to_club_without_membership(self):
        stranger = User.objects.create_user("stranger", password="pass-12345-x")
        other = create_club("Club B", "Madrid", stranger)
        self.client.login(username="viewer", password="pass-12345-x")
        self.assertEqual(self.client.post(reverse("switch_club"), {"club_id": other.id}).status_code, 404)

    def test_last_admin_is_protected(self):
        self.client.login(username="owner", password="pass-12345-x")
        owner_membership = Membership.objects.get(user=self.owner, club=self.club)
        self.client.post(reverse("remove_member", args=[owner_membership.public_id]))
        self.assertTrue(Membership.objects.filter(pk=owner_membership.pk).exists())

    def test_register_club_creates_user_club_and_membership(self):
        response = self.client.post(reverse("register_club"), {
            "name": "Nuevo Club", "location": "Cádiz", "gender": "F", "country": "MX", "division": "1000",
            "username": "fundador", "email": "f@example.com",
            "password1": "Clave-Segura-123", "password2": "Clave-Segura-123",
            "player-name": "Ana", "player-last_name": "Ruiz",
        })
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        club = Club.objects.get(name="Nuevo Club")
        self.assertTrue(Membership.objects.get(user__username="fundador", club=club).is_admin)
        self.assertEqual(club.own_team.name, "Nuevo Club")
        self.assertEqual((club.own_team.gender, club.own_team.country), ("F", "MX"))


class AssignDefaultClubCommandTests(TestCase):
    def test_assigns_legacy_data(self):
        user = User.objects.create_user("legacy", password="x")
        own = Team.objects.create(name="LOS GLADIADORES", location="Sevilla", in_group=True)
        rival = Team.objects.create(name="Rival", location="X", in_group=True)
        Player.objects.create(name="Old", last_name="Player", team=own)
        Match.objects.create(local=own, visiting=rival, start_date=datetime.date(2024, 10, 1))

        call_command("assign_default_club", stdout=io.StringIO())
        call_command("assign_default_club", stdout=io.StringIO())  # idempotente

        club = Club.objects.get()
        own.refresh_from_db()
        self.assertTrue(own.is_own)
        self.assertEqual(club.own_team, own)
        self.assertFalse(Team.objects.filter(club__isnull=True).exists())
        self.assertFalse(Player.objects.filter(club__isnull=True).exists())
        self.assertFalse(Match.objects.filter(club__isnull=True).exists())
        self.assertTrue(Membership.objects.get(user=user, club=club).is_admin)


class AssignDefaultClubMergeTests(TestCase):
    def test_merges_own_team_created_at_signup_into_legacy_team(self):
        """Caso real: el club se registró por la web (crea un equipo propio vacío)
        y el equipo antiguo con el historial se quedó sin club."""
        user = User.objects.create_user("legacy", password="x")
        legacy = Team.objects.create(name="LOS GLADIADORES", location="Sevilla", in_group=True)
        rival = Team.objects.create(name="Rival", location="X", in_group=True)
        club = create_club("LOS GLADIADORES", "Sevilla", user)
        duplicate = club.own_team
        new_player = Player.objects.create(club=club, name="Nuevo", last_name="Jugador")
        Match.objects.create(club=club, local=legacy, visiting=rival, start_date=datetime.date(2025, 10, 1),
                             result="Victoria Local", draft_mode=False)

        call_command("assign_default_club", stdout=io.StringIO())

        legacy.refresh_from_db()
        new_player.refresh_from_db()
        self.assertEqual(club.own_team, legacy)
        self.assertEqual(legacy.club, club)
        self.assertFalse(Team.objects.filter(pk=duplicate.pk).exists())
        self.assertEqual(new_player.team, legacy)

        self.client.login(username="legacy", password="x")
        response = self.client.get(reverse("team_statistics"))
        self.assertEqual(response.context["won_matches"], 1)
        self.assertEqual(response.context["lost_matches"], 0)


class HomeTests(TestCase):
    """Portada: logo, próximo partido con ubicación y jugador/pareja en racha."""

    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        self.own = self.club.own_team
        self.rival = Team.objects.create(club=self.club, name="Rival", location="Calle Real 1, Sevilla", in_group=True)
        self.today = datetime.date.today()
        self.client.login(username="admin", password="pass-12345")

    def test_anonymous_gets_landing(self):
        self.client.logout()
        self.assertTemplateUsed(self.client.get(reverse("home")), "landing.html")

    def test_match_copies_local_location(self):
        match = Match.objects.create(club=self.club, local=self.rival, visiting=self.own, start_date=self.today)
        self.assertEqual(match.location, "Calle Real 1, Sevilla")
        self.assertEqual(match.maps_url,
                         "https://www.google.com/maps/search/?api=1&query=Calle%20Real%201%2C%20Sevilla")

        # Es una copia: cambiar la sede del equipo no toca los partidos ya creados
        self.rival.location = "Otra sede"
        self.rival.save()
        match.refresh_from_db()
        self.assertEqual(match.location, "Calle Real 1, Sevilla")

    def test_create_match_view_copies_location(self):
        self.client.post(reverse("create_match"), {
            "local": self.rival.id, "visiting": self.own.id, "start_date": self.today.isoformat(),
        })
        self.assertEqual(Match.objects.get().location, "Calle Real 1, Sevilla")

    def test_fill_match_locations_command(self):
        match = Match.objects.create(club=self.club, local=self.rival, visiting=self.own, start_date=self.today)
        Match.objects.filter(pk=match.pk).update(location="")
        call_command("fill_match_locations", stdout=io.StringIO())
        match.refresh_from_db()
        self.assertEqual(match.location, "Calle Real 1, Sevilla")

    def test_next_match_is_first_from_today(self):
        Match.objects.create(club=self.club, local=self.own, visiting=self.rival,
                             start_date=self.today - datetime.timedelta(days=1))
        later = Match.objects.create(club=self.club, local=self.own, visiting=self.rival,
                                     start_date=self.today + datetime.timedelta(days=10))
        soon = Match.objects.create(club=self.club, local=self.rival, visiting=self.own,
                                    start_date=self.today + datetime.timedelta(days=3))
        other = create_club("Club B", "Madrid", User.objects.create_user("b", password="x"))
        Match.objects.create(club=other, local=other.own_team, visiting=other.own_team, start_date=self.today)

        response = self.client.get(reverse("home"))
        self.assertEqual(response.context["next_match"], soon)
        self.assertEqual(response.context["days_left"], 3)
        self.assertContains(response, soon.maps_url.replace("&", "&amp;"))
        self.assertNotEqual(response.context["next_match"], later)

    def test_empty_home(self):
        response = self.client.get(reverse("home"))
        self.assertIsNone(response.context["next_match"])
        self.assertContains(response, "No hay partidos programados.")
        self.assertContains(response, "Nadie encadena victorias ahora mismo.")

    def test_hot_player_and_pair(self):
        ana = Player.objects.create(club=self.club, name="Ana", last_name="Alpha")
        bea = Player.objects.create(club=self.club, name="Bea", last_name="Beta")
        for n, day in enumerate((1, 2), start=1):
            m = Match.objects.create(club=self.club, local=self.own, visiting=self.rival, draft_mode=False,
                                     start_date=self.today - datetime.timedelta(days=10 - day))
            Game.objects.create(match=m, n_game=1, score=3, winner="Local", draft_mode=False,
                                player_1_local=ana, player_2_local=bea)

        response = self.client.get(reverse("home"))
        self.assertEqual(response.context["hot_player"]["streak"], 2)
        self.assertEqual(response.context["hot_pair"]["label"], "ANA ALPHA / BEA BETA")
        self.assertContains(response, "2 victorias seguidas")
        # El botón abre la pareja con sus identificadores públicos (con el id interno daba 404)
        self.assertContains(response, f"?p1={ana.public_id}&amp;p2={bea.public_id}")


    def test_pages_load_hide_on_scroll_navigation(self):
        # Cabecera y barra inferior se esconden al bajar (static/js/nav.js)
        self.assertContains(self.client.get(reverse("home")), "js/nav.js")
        self.client.logout()
        self.assertContains(self.client.get(reverse("home")), "js/nav.js")


class AdoptRepoMigrationsTests(TestCase):
    """Bases de datos creadas cuando cada entorno generaba sus propias migraciones."""

    def _run(self, *args):
        out = io.StringIO()
        call_command("adopt_repo_migrations", *args, stdout=out)
        return out.getvalue()

    def _project_history(self):
        from django.db import connection
        from django.db.migrations.recorder import MigrationRecorder
        from core.management.commands.adopt_repo_migrations import PROJECT_APPS
        return {k for k in MigrationRecorder(connection).applied_migrations() if k[0] in PROJECT_APPS}

    def test_nothing_to_do_when_history_matches_the_repo(self):
        self.assertIn("Nada que hacer", self._run())

    def test_replaces_local_history_with_repo_initials(self):
        from django.db import connection
        from django.db.migrations.recorder import MigrationRecorder
        recorder = MigrationRecorder(connection)
        recorder.migration_qs.filter(app__in=["core", "match", "backoffice"]).delete()
        for key in [("core", "0001_initial"), ("core", "0007_invitation"), ("match", "0004_match_location")]:
            recorder.record_applied(*key)

        output = self._run("--dry-run")
        self.assertIn("core.0007_invitation", output)
        self.assertIn(("core", "0007_invitation"), self._project_history())

        output = self._run()
        self.assertIn("Historial adaptado", output)
        history = self._project_history()
        self.assertNotIn(("core", "0007_invitation"), history)
        self.assertNotIn(("match", "0004_match_location"), history)
        self.assertIn(("match", "0001_initial"), history)
        self.assertIn(("backoffice", "0001_initial"), history)
        # Las posteriores las aplica migrate.
        self.assertNotIn(("backoffice", "0002_scheduledjob_heartbeat"), history)



class CopySqliteToDbTests(SimpleTestCase):
    """
    copy_sqlite_to_db de un SQLite a otro (en producción el destino es PostgreSQL). Se
    ejecuta en procesos aparte, cada uno con su DATABASE_URL, como se usa de verdad.
    """
    SOURCE_DATA = (
        "import datetime\n"
        "from django.contrib.auth import get_user_model\n"
        "from call.models import Call\n"
        "from core.models import Club, Membership\n"
        "from match.models import Match\n"
        "from players.models import Player\n"
        "from team.models import Team\n"
        "user = get_user_model().objects.create_user('capitan', 'c@example.com', 'pass-12345')\n"
        "club = Club.objects.create(name='Club Origen')\n"
        "Membership.objects.create(user=user, club=club, role='admin')\n"
        "own = Team.objects.create(club=club, name='Club Origen', is_own=True, location='Sevilla')\n"
        "rival = Team.objects.create(club=club, name='Rival', location='Sevilla')\n"
        "players = [Player.objects.create(club=club, team=own, name=f'J{i}', last_name='X') for i in range(4)]\n"
        "match = Match.objects.create(club=club, local=own, visiting=rival, start_date=datetime.date(2026, 10, 1))\n"
        "Call.objects.create(match=match).players.set(players)\n"
    )
    TARGET_CHECK = (
        "from django.contrib.auth import get_user_model\n"
        "from call.models import Call\n"
        "from players.models import Player\n"
        "club_players = Player.objects.filter(club__name='Club Origen')\n"
        "new = Player.objects.create(club=club_players[0].club, name='Nuevo', last_name='Y')\n"
        "print(club_players.count() - 1, Call.objects.get().players.count(),\n"
        "      get_user_model().objects.get(username='capitan').check_password('pass-12345'))\n"
    )

    def _manage(self, url, *args, check=True):
        import os
        import subprocess
        import sys
        from django.conf import settings
        env = {**os.environ, "DJANGO_DEBUG": "True", "DATABASE_URL": url}
        return subprocess.run([sys.executable, "manage.py", *args], cwd=settings.BASE_DIR, env=env,
                              capture_output=True, text=True, check=check)

    def setUp(self):
        import tempfile
        from pathlib import Path
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.source = Path(folder.name) / "origen.sqlite3"
        self.target_url = f"sqlite:///{Path(folder.name) / 'destino.sqlite3'}"
        self._manage(f"sqlite:///{self.source}", "migrate", "-v0")
        self._manage(f"sqlite:///{self.source}", "shell", "-c", self.SOURCE_DATA)
        self._manage(self.target_url, "migrate", "-v0")

    def test_copies_everything_and_counts_match(self):
        result = self._manage(self.target_url, "copy_sqlite_to_db", str(self.source), "--any-target")
        self.assertIn("todas las tablas coinciden", result.stdout)
        # Jugadores y convocados copiados, contraseña intacta y los ids nuevos no chocan.
        check = self._manage(self.target_url, "shell", "-c", self.TARGET_CHECK)
        self.assertEqual(check.stdout.split(), ["4", "4", "True"])

        again = self._manage(self.target_url, "copy_sqlite_to_db", str(self.source), "--any-target", check=False)
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("ya tiene datos", again.stderr)

    def test_needs_postgresql_unless_forced(self):
        result = self._manage(self.target_url, "copy_sqlite_to_db", str(self.source), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no es PostgreSQL", result.stderr)
