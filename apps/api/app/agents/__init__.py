"""Agent portal/commissions domain.

NEEDS_CONFIRMATION - BLOCKED_BY_DECISION(DEC-002). No role, screen, or module for this
domain exists in the approved SRC-006/SRC-007 catalogue; see
docs/decisions/DECISION_REGISTER.md DEC-002 and docs/specs/PRODUCT_REQUIREMENTS.md #13.
This package is a reserved, frozen namespace only - do not add endpoints, services, or
models here until DEC-002 is approved. Existing agent-backed tables
(AgentStudent, AgentCommission) remain in the flat app/models.py until that happens.
"""
