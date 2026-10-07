import json
import os
import secrets
from dataclasses import dataclass

from .db import Problem


@dataclass(frozen=True)
class Identity:
    tenant: str
    user: str
    role: str


DEMO_KEYS = {
    "demo-analyst": Identity("northline", "alex", "analyst"),
    "demo-reviewer": Identity("northline", "jordan", "reviewer"),
    "demo-other": Identity("other", "sam", "analyst"),
}


def credentials(demo):
    if demo:
        return DEMO_KEYS
    raw = json.loads(os.environ.get("BRICKLINE_KEYS_JSON", "{}"))
    parsed = {}
    for key, value in raw.items():
        who = Identity(**value)
        if len(key) < 24 or who.role not in {"analyst", "reviewer"} or not who.tenant or not who.user:
            raise RuntimeError("Configure strong keys and explicit tenant/user/role identities")
        parsed[key] = who
    if not parsed:
        raise RuntimeError("Configure BRICKLINE_KEYS_JSON or explicitly start the local demo")
    return parsed


def authenticate(keys, supplied):
    for key, identity in keys.items():
        if supplied and secrets.compare_digest(supplied, key):
            return identity
    raise Problem("A valid API key is required", 401)
