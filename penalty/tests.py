"""Pruebas de las advertencias: motivo, detalle, «Deshacer», «Quitar» y aislamiento entre clubes."""
import datetime

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.utils import translation
from django.urls import reverse

from call.models import Call
from callLog.models import CallLog
from core.models import Membership
from core.services import create_club
from match.models import Match
from penalty import models as penalty_models
from penalty.models import Penalty, reason_text
from penalty.views import UNDO_TAG
from players.models import Player
from team.models import Team

User = get_user_model()
PASSWORD = "pass-12345-x"


class PenaltyBase(TestCase):
    """Un club con capitán, un miembro, dos jugadores en el equipo y una convocatoria."""

    def setUp(self):
        self.captain = User.objects.create_user("captain", password=PASSWORD)
        self.club = create_club("Club A", "Sevilla", self.captain)
        self.member = User.objects.create_user("member", password=PASSWORD)
        Membership.objects.create(user=self.member, club=self.club, role=Membership.MEMBER)
        rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=rival,
                                          start_date=datetime.date(2025, 10, 1))
        self.call = Call.objects.create(match=self.match, draft_mode=False)
        CallLog.objects.create(call=self.call, text="")
        self.ana = Player.objects.create(club=self.club, name="Ana", last_name="Alpha")
        self.zoe = Player.objects.create(club=self.club, name="Zoe", last_name="Zeta")
        self.gone = Player.objects.create(club=self.club, name="Bea", last_name="Beta", in_team=False)
        self.client.login(username="captain", password=PASSWORD)

    def apply(self, players, **data):
        """Aplica una advertencia a ``players`` con los datos del formulario."""
        return self.client.post(reverse("create_penalty", args=[self.call.public_id]),
                                {"players": [p.id for p in players], **data})

    def messages(self, response):
        """Mensajes pendientes de la respuesta (con su ``extra_tags``)."""
        return list(get_messages(response.wsgi_request))


class ReasonTextTests(TestCase):
    def test_reason_text_combines_kind_and_detail(self):
        self.assertEqual(reason_text(penalty_models.LATE, "20 min"), "Llegó tarde: 20 min")
        self.assertEqual(reason_text(penalty_models.LATE, ""), "Llegó tarde")
        self.assertEqual(reason_text(penalty_models.OTHER, "Sin pelotas"), "Sin pelotas")
        self.assertEqual(reason_text(penalty_models.OTHER, ""), "Otro")

    def test_reason_text_is_translated(self):
        with translation.override("en"):
            self.assertEqual(reason_text(penalty_models.NO_SHOW, ""), "Did not show up")
            self.assertEqual(reason_text(penalty_models.LATE_DROP, "gripe"), "Late withdrawal: gripe")

    def test_unknown_kind_falls_back_to_other(self):
        self.assertEqual(reason_text("???", "texto"), "texto")


class CreatePenaltyTests(PenaltyBase):
    def test_creates_one_penalty_per_current_player_with_kind_and_detail(self):
        response = self.apply([self.ana, self.zoe, self.gone], kind="late", reason="20 min")
        self.assertRedirects(response, reverse("call_for_match", args=[self.match.public_id]))
        rows = Penalty.objects.order_by("player__name")
        self.assertEqual([p.player.name for p in rows], ["Ana", "Zoe"])
        self.assertEqual({(p.kind, p.reason) for p in rows}, {("late", "20 min")})
        self.assertEqual(rows[0].display_reason, "Llegó tarde: 20 min")

    def test_success_message_carries_the_undo_url(self):
        response = self.apply([self.ana], kind="no_show")
        tags = [m.extra_tags for m in self.messages(response) if m.extra_tags]
        penalty = Penalty.objects.get()
        self.assertEqual(tags, [UNDO_TAG + reverse("delete_penalty") + "?ids=" + penalty.public_id])

    def test_toast_shows_the_undo_button(self):
        self.apply([self.ana], kind="no_show")
        page = self.client.get(reverse("call_for_match", args=[self.match.public_id]))
        self.assertContains(page, reverse("delete_penalty"))
        self.assertContains(page, "z-toast-undo")

    def test_kind_is_required_and_must_be_valid(self):
        for data in ({}, {"kind": ""}, {"kind": "inventado"}):
            response = self.apply([self.ana], **data)
            self.assertRedirects(response, reverse("view_call_log", args=[self.call.public_id]))
        self.assertFalse(Penalty.objects.exists())

    def test_other_requires_a_detail(self):
        self.apply([self.ana], kind="other", reason="   ")
        self.assertFalse(Penalty.objects.exists())
        self.apply([self.ana], kind="other", reason="Sin pelotas")
        self.assertEqual(Penalty.objects.get().display_reason, "Sin pelotas")

    def test_detail_is_trimmed_to_the_field_length(self):
        self.apply([self.ana], kind="conduct", reason="x" * 300)
        self.assertEqual(len(Penalty.objects.get().reason), penalty_models.REASON_MAX_LENGTH)

    def test_needs_at_least_one_current_player(self):
        response = self.apply([self.gone], kind="late")
        self.assertRedirects(response, reverse("view_call_log", args=[self.call.public_id]))
        self.assertFalse(Penalty.objects.exists())

    def test_member_cannot_create(self):
        self.client.login(username="member", password=PASSWORD)
        self.apply([self.ana], kind="late")
        self.assertFalse(Penalty.objects.exists())


class DeletePenaltyTests(PenaltyBase):
    def setUp(self):
        super().setUp()
        self.p1 = Penalty.objects.create(player=self.ana, call=self.call, kind="late")
        self.p2 = Penalty.objects.create(player=self.zoe, call=self.call, kind="no_show")

    def delete(self, *penalties, **extra):
        """POST de retirada con los identificadores en la URL, como el botón «Deshacer»."""
        ids = ",".join(p.public_id for p in penalties)
        return self.client.post(reverse("delete_penalty") + "?ids=" + ids, **extra)

    def test_undo_removes_all_listed_penalties(self):
        response = self.delete(self.p1, self.p2)
        self.assertRedirects(response, reverse("view_call_log", args=[self.call.public_id]))
        self.assertFalse(Penalty.objects.exists())

    def test_removes_only_the_listed_one(self):
        self.delete(self.p1)
        self.assertEqual(list(Penalty.objects.all()), [self.p2])

    def test_ids_can_come_in_the_post_body(self):
        self.client.post(reverse("delete_penalty"), {"ids": self.p2.public_id})
        self.assertEqual(list(Penalty.objects.all()), [self.p1])

    def test_get_is_not_allowed(self):
        response = self.client.get(reverse("delete_penalty") + "?ids=" + self.p1.public_id)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(Penalty.objects.count(), 2)

    def test_member_cannot_remove(self):
        self.client.login(username="member", password=PASSWORD)
        response = self.delete(self.p1)
        self.assertEqual(Penalty.objects.count(), 2)
        self.assertNotEqual(response.status_code, 200)

    def test_penalties_of_other_clubs_are_untouched(self):
        other_user = User.objects.create_user("other", password=PASSWORD)
        other = create_club("Club B", "Madrid", other_user)
        rival = Team.objects.create(club=other, name="R", location="Y", in_group=True)
        match = Match.objects.create(club=other, local=other.own_team, visiting=rival, start_date=datetime.date(2025, 10, 2))
        call = Call.objects.create(match=match, draft_mode=False)
        player = Player.objects.create(club=other, name="Eva", last_name="E")
        foreign = Penalty.objects.create(player=player, call=call, kind="late")
        response = self.delete(foreign)
        self.assertRedirects(response, reverse("list_match"))
        self.assertTrue(Penalty.objects.filter(pk=foreign.pk).exists())

    def test_unknown_ids_do_nothing(self):
        response = self.client.post(reverse("delete_penalty") + "?ids=PENxxxxxxxxxxxx")
        self.assertRedirects(response, reverse("list_match"))
        self.assertEqual(Penalty.objects.count(), 2)


class CallLogPageTests(PenaltyBase):
    def test_captain_sees_form_with_kinds_and_existing_penalties(self):
        Penalty.objects.create(player=self.ana, call=self.call, kind="late", reason="20 min")
        page = self.client.get(reverse("view_call_log", args=[self.call.public_id]))
        self.assertContains(page, 'name="kind"')
        self.assertContains(page, "Llegó tarde: 20 min")
        self.assertContains(page, reverse("delete_penalty"))

    def test_member_sees_neither_form_nor_penalty_list(self):
        Penalty.objects.create(player=self.ana, call=self.call, kind="late")
        self.client.login(username="member", password=PASSWORD)
        page = self.client.get(reverse("view_call_log", args=[self.call.public_id]))
        self.assertNotContains(page, 'name="kind"')
        self.assertNotContains(page, reverse("delete_penalty"))

    def test_call_selector_lists_readable_reasons(self):
        from match.views import selectable_players
        Penalty.objects.create(player=self.ana, call=self.call, kind="late", reason="20 min")
        ana = next(p for p in selectable_players(self.club) if p.id == self.ana.id)
        self.assertEqual(ana.penalty_reasons, ["Llegó tarde: 20 min"])

    def test_warning_statistics_show_the_reason(self):
        Penalty.objects.create(player=self.ana, call=self.call, kind="late_drop")
        page = self.client.get(reverse("warnings_statistics"), {"season": "all"})
        self.assertContains(page, "Baja de última hora")


class LegacyMigrationTests(TestCase):
    def test_automatic_texts_are_cleared_and_free_text_is_kept(self):
        """La limpieza de la migración 0003 vacía el texto automático y conserva el escrito a mano."""
        import importlib
        from django.apps import apps
        migration = importlib.import_module("penalty.migrations.0003_penalty_kind")
        user = User.objects.create_user("c", password=PASSWORD)
        club = create_club("Club", "Sevilla", user)
        rival = Team.objects.create(club=club, name="R", location="Y", in_group=True)
        match = Match.objects.create(club=club, local=club.own_team, visiting=rival, start_date=datetime.date(2025, 10, 1))
        call = Call.objects.create(match=match)
        player = Player.objects.create(club=club, name="Ana", last_name="A")
        auto = Penalty.objects.create(player=player, call=call, reason="Advertencia en el partido A VS B.")
        plain = Penalty.objects.create(player=player, call=call, reason="Advertencia")
        free = Penalty.objects.create(player=player, call=call, reason="Retraso")
        migration.clear_auto_reasons(apps, None)
        for pen in (auto, plain, free):
            pen.refresh_from_db()
        self.assertEqual((auto.reason, plain.reason, free.reason), ("", "", "Retraso"))
        self.assertEqual(auto.display_reason, "Otro")
        self.assertEqual(free.display_reason, "Retraso")
