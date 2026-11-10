"""Versioned local permission identity, interpreted only by trusted controller code."""

from arf.plan_models import sha

POLICY_VERSION = "offline-demo-1"
POLICY = b"VS-002: explicit local operator; demo_mean only; strict fresh context; no automatic execution."
POLICY_SHA256 = sha(POLICY)
