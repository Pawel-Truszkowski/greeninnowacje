from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsVolunteer

from .selectors import achievements
from .services import award_badges


@api_view(["GET"])
@permission_classes([IsVolunteer])
def my_achievements(request):
    """The achievements page as JSON — for a future mobile app. Read-only: nothing marked seen."""
    award_badges(request.user)
    data = achievements(request.user)
    level, ranking = data["level"], data["ranking"]

    def row(entry):
        return {
            "rank": entry.rank,
            "display_name": entry.display_name,
            "points": entry.points,
            "is_me": entry.is_me,
        }

    return Response(
        {
            "points": data["points"],
            "level": {
                "number": level.number,
                "name": level.name,
                "icon": level.icon,
                "threshold": level.threshold,
                "next_threshold": level.next_threshold,
                "next_name": level.next_name,
            },
            "badges": [
                {
                    "code": item["badge"].code,
                    "name": item["badge"].name,
                    "icon": item["badge"].icon,
                    "how": item["badge"].how,
                    "earned": item["earned"],
                    "awarded_at": item["awarded_at"],
                }
                for item in data["badges"]
            ],
            "ranking": {
                "days": ranking["days"],
                "rows": [row(entry) for entry in ranking["rows"]],
                "me": row(ranking["me"]) if ranking["me"] else None,
            },
        }
    )
