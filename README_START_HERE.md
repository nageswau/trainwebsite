# EduSphere Claude Code — From Scratch Final Package v3

This is a clean, no-assumption workflow rebuilt after reviewing:
- the original requirements,
- quotation,
- revised technology-stack request,
- application blueprint,
- workbook/backlog/test catalogue,
- meeting transcripts,
- previous Claude prompts,
- the supplied Canva URL / connected Canva design metadata.

## Critical correction

Earlier packages allowed some derived documents to look like final truth.
This version does not.

Everything starts as evidence. The chain is:

Evidence -> Explicit Decision -> BRD -> PRD -> Feature Catalogue -> UX ->
Architecture -> Contracts -> Test Strategy -> Implementation.

## Canva status

Reference:
https://vnsitcareer.my.canva.site/onecampus-erp-customer-friendly-responsive-ux

Connected design:
`DAHRWCa0RLw — OneCampus ERP — Customer-Friendly Responsive UX`

During this review, Canva rich-text extraction was empty and the public URL was not fetchable by the
public web tool. Therefore no screen-by-screen visual claims were made.

Claude Code must either:
- actually access/render it and record evidence, or
- mark it inaccessible and ask for an inspectable export.

## First commands on Windows

```powershell
cd C:\Projects\EduSphere\edusphere_claude_from_scratch
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\preflight.ps1
claude
```

Then paste:

```text
Read CLAUDE.md completely.

Execute:
prompts/00_BOOTSTRAP_AND_EVIDENCE_INVENTORY.md

NO CODE.
Do not infer approvals.
Stop after the evidence inventory.
```

## Do not install stack-specific skills yet

First confirm `DEC-TECH-001`.

If Next.js + FastAPI is explicitly approved:

```powershell
.\scripts\setup-skills-after-stack-approval.ps1 -InstallProposedNextFastAPIStack
```

Start a new Claude session after skill installation.

## Prompt order

Read `prompts/PROMPT_INDEX.md`.

The feature-creation prompt is:
`prompts/06_MASTER_FEATURE_CATALOG.md`

## Original source evidence

Located under:
`docs/sources/`

Keep it immutable and out of Git by default.

## Master procedure

Read:
`EduSphere_Claude_From_Scratch_Master_Procedure.txt`
