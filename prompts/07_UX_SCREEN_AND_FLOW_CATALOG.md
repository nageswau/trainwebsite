# 07 — UX Screen, Route and Flow Catalogue

Prerequisite:
Feature catalogue is approved.

Read:
- approved features/ACs
- PRD/BRD
- UX reference audit
- old screen inventory only as derived input

NO CODE.

For every approved UI feature define only the UI needed to satisfy its requirements.

Create:
- screen/route ID
- role
- route/purpose
- linked Feature IDs
- entry points
- required data
- key actions
- empty/loading/error states
- permissions/resource scope
- responsive behavior
- accessibility requirements
- desktop/tablet/mobile behavior
- visual-reference mapping if actually inspectable
- acceptance evidence needed

Apply the confirmed UX principle:
clear, concise, minimal clutter, only relevant actions for the logged-in user.

Find:
- FEATURE_WITHOUT_REQUIRED_SCREEN
- SCREEN_WITHOUT_APPROVED_FEATURE
- DUPLICATE_SCREEN
- ROLE_NAVIGATION_CONFLICT
- UX_REFERENCE_CONFLICT

Do not claim visual parity with Canva unless it was actually inspected.

Create:
- `docs/ux/SCREEN_CATALOG.md`
- `docs/ux/ROLE_NAVIGATION.md`
- `docs/ux/USER_FLOW_MAP.md`
- `docs/ux/RESPONSIVE_RULES.md`
- `docs/ux/ACCESSIBILITY_RULES.md`

STOP for UX approval.
