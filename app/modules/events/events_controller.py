from flask import Blueprint, Response, stream_with_context

from app.common.event_bus import events
from app.modules.auth.jwt_guard import jwt_required

live = Blueprint("events", __name__)


@live.get("/events")
@jwt_required
def stream():
    """Live updates: likes, comments and published posts. Events carry ids and counts only,
    never content, so a viewer fetches anything private through the normal guarded routes."""
    return Response(stream_with_context(events.stream()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
