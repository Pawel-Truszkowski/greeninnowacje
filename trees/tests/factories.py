"""Helpers for building tree history in tests."""

from datetime import timedelta

from django.utils import timezone

from trees.models import Assignment, Watering


def water(tree, user, days_ago=0):
    return Watering.objects.create(
        tree=tree, user=user, watered_at=timezone.now() - timedelta(days=days_ago)
    )


def assign(tree, user):
    return Assignment.objects.create(tree=tree, user=user)
