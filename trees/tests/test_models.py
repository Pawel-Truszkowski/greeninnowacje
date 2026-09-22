import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.utils import timezone

from factories import UserFactory
from trees.models import AppendOnlyError, Assignment, Watering

pytestmark = pytest.mark.django_db


@pytest.fixture
def watering(tree, user):
    return Watering.objects.create(tree=tree, user=user)


class TestWateringAppendOnly:
    def test_orm_update_blocked(self, watering):
        watering.watered_at = timezone.now()
        with pytest.raises(AppendOnlyError):
            watering.save()

    def test_orm_delete_blocked(self, watering):
        with pytest.raises(AppendOnlyError):
            watering.delete()

    def test_queryset_update_and_delete_blocked(self, watering):
        with pytest.raises(AppendOnlyError):
            Watering.objects.filter(pk=watering.pk).update(watered_at=timezone.now())
        with pytest.raises(AppendOnlyError):
            Watering.objects.filter(pk=watering.pk).delete()

    @pytest.mark.parametrize(
        "sql",
        [
            "UPDATE waterings SET watered_at = now() WHERE id = %s",
            "DELETE FROM waterings WHERE id = %s",
        ],
    )
    def test_raw_sql_blocked_by_db_trigger(self, watering, sql):
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(sql, [watering.pk])
        assert Watering.objects.filter(pk=watering.pk).exists()


class TestSingleActiveCaretaker:
    def test_second_active_assignment_rejected(self, tree, user):
        Assignment.objects.create(tree=tree, user=user)
        with pytest.raises(IntegrityError), transaction.atomic():
            Assignment.objects.create(tree=tree, user=UserFactory())

    def test_new_caretaker_after_previous_ended(self, tree, user):
        first = Assignment.objects.create(tree=tree, user=user)
        first.ended_at = timezone.now()
        first.save()
        Assignment.objects.create(tree=tree, user=UserFactory())
        assert tree.assignments.filter(ended_at__isnull=True).count() == 1
