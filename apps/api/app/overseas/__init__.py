"""Overseas education/application management domain.

NEEDS_CONFIRMATION - BLOCKED_BY_DECISION(DEC-001). No module, screen, or role for this
domain exists in the approved SRC-006/SRC-007 catalogue; see
docs/decisions/DECISION_REGISTER.md DEC-001 and docs/specs/PRODUCT_REQUIREMENTS.md #12.
This package is a reserved, frozen namespace only - do not add endpoints, services, or
models here until DEC-001 is approved. Existing overseas-backed tables
(Country, University, OverseasApplication, etc.) remain in the flat app/models.py
until that happens; they are not moved or extended by this package.
"""
