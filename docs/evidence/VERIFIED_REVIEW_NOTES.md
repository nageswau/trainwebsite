# Verified Review Notes — 1 September 2026

This file records facts verified during preparation of this package. It deliberately separates
source facts from unresolved decisions.

## 1. Original-source duplicates verified by SHA-256

The following three Word files are byte-for-byte identical:
- `Edusphere UK Website (1)(1).docx`
- `Edusphere UK Website(1)(1).docx`
- `Edusphere UK Website(2).docx`

The following two transcript files are byte-for-byte identical:
- `Pasted text (2)(2).txt`
- `Pasted text (3).txt`

See `SOURCE_MANIFEST.csv` for exact hashes.

Do not treat duplicate filenames as independent evidence.

## 2. Requirements conflict verified

The original website requirement and 30 July 2026 quotation describe:
- Visitor/Student/Trainer/Admin as the main roles.
- Employer Portal as a future phase.
- Admin CRM functionality in the older scope/quotation.

The later 1 August application blueprint says:
- Custom CRM is excluded and replaced by admissions handoff only.
- Employer Portal is included in the current scope.
- Visitor/Student/Trainer/Admin/Employer are current roles.

This is a real conflict. The later blueprint calls its position "approved", but this package does
NOT automatically treat that label as final client approval. Claude must require an explicit
approval record or user/client confirmation before freezing scope.

## 3. Tech-stack evidence verified

`Revised Tech stack for the proposal(1).docx` states a preferred stack:
- Next.js + TypeScript
- FastAPI
- PostgreSQL
- AWS S3
- AWS EC2 + RDS
- JWT with Google login
- GitHub
- scalability goal of 10,000+ users

The later blueprint recommends:
- modular monolith
- ECS Fargate (or ECS/EC2 fallback)
- RDS PostgreSQL
- Redis + Celery
- private S3
- GitHub Actions/ECR/ECS

These are source proposals/recommendations until the technical decision is explicitly approved.

## 4. Deployment evidence verified

A meeting transcript includes a statement agreeing to AWS for production, while development could
remain outside AWS/local.

Later discussion in this ChatGPT conversation compared DigitalOcean with AWS Fargate, but that is
not an original client-source approval.

Therefore the final package treats cloud deployment as an explicit decision:
`DEC-INFRA-001`.

No provider-specific production infrastructure should be generated until that decision is confirmed.

## 5. Overseas Education / Agent scope verified as newer meeting requirements

Meeting transcripts introduce substantial requirements not represented in the 1 August blueprint,
including:
- countries/destinations, universities and courses
- admission process stages
- financial/visa documentation
- visa checklist/interview/tracking
- scholarships
- events
- overseas login
- agent registration/login
- agent student submission/tracking
- direct-student document upload
- eligibility evaluation and university/course selection
- application status tracking
- email/WhatsApp status updates
- agent commissions/claims

These are real transcript requests, but the transcript also contains future-oriented wording such
as "later on". Therefore Claude must NOT automatically classify the whole Overseas/Agent domain as
current release. It must be resolved by Product Decision IDs.

## 6. UX direction verified from meeting transcript

The client asks for a portal that is "very clear and crispy", with few relevant options and without
clutter/confusion. Treat this as a UX principle, not as a complete screen specification.

## 7. Internal meeting platform verified as separate

A transcript discusses building an internal meeting/recording platform because of simultaneous
recording limitations, then explicitly says it can be a separate project.

Therefore it must remain OUTSIDE the main EduSphere implementation unless a later explicit decision
moves it into scope.

## 8. Workbook quality facts verified

Workbook:
`Edusphere_Master_Backlog_RBAC_API_Test_Catalogue(1).xlsx`

Verified:
- 824 test cases.
- All 824 Test_Cases status values are `Draft`.
- RTM has modules with incomplete screen/API/test mappings.
- The generated test catalogue contains assumptions that must be audited.

Examples verified:
- `/api/v1/certificates/verify/{code}` has a generated test requiring authentication/resource scope,
  even though the blueprint describes Visitor certificate verification.
- The same lookup route receives a generic pagination/filtering boundary test.
- `/api/v1/public/content/{type}` has generic authentication/RBAC and pagination assumptions.
- `/api/v1/payments/webhooks/{provider}` has a generic end-user authentication/RBAC test even though
  provider webhooks normally require provider-specific signature/secret/replay semantics.

Do not implement incorrect behavior merely to make these draft tests pass.

## 9. Canva URL review status

Published URL supplied earlier:
`https://vnsitcareer.my.canva.site/onecampus-erp-customer-friendly-responsive-ux`

Connected Canva search resolves an exact design:
- Design ID: `DAHRWCa0RLw`
- Title: `OneCampus ERP — Customer-Friendly Responsive UX`
- Page count: 1
- Last connector-reported update: 29 August 2026

The Canva connector returned empty rich-text content for this design. The public published URL also
could not be fetched by the public web tool during this review.

Therefore:
- the URL is a valid UX reference,
- but this package does NOT claim a screen-by-screen or pixel-by-pixel inspection,
- no product feature may be inferred solely from that inaccessible design,
- if Claude Code cannot access/render the URL itself, request/export screenshots, PDF, HTML or another
  inspectable representation before claiming visual parity.

## 10. No-assumption rule

Nothing in this package should be treated as final merely because an older derived document uses the
word "approved".

Final scope/stack/provider/UX authority must be represented by explicit Product Decision and Approval
records created during the workflow.
