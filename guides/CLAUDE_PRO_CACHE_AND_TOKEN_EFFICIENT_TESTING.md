# Claude Usage / Cache / Token-Efficient Testing

## Claude Pro
Use Pro for planning and moderate coding. Heavy daily full-stack implementation may hit limits.
Do not architect the workflow around unlimited model usage.

## Sessions
Use fresh sessions for major phases/modules. Durable truth lives in approved docs, not one giant chat.

## .claude-cache
Do not remove it every time. Disk cache is not the main source of model token/context usage.

## webapp-testing
Useful for focused UI/E2E validation.
The expensive part is not "having the skill"; usage grows when Claude repeatedly reads DOMs,
screenshots, logs and retries.

Preferred:
Claude writes deterministic test -> local Playwright/pytest runs -> compact summary ->
Claude opens only failing artifacts.

For PASS:
- command
- total/pass/fail/skip
- duration

For FAIL:
- failed IDs
- relevant assertion/stack
- relevant browser console/network
- failing screenshot/trace only

Do not load all 824 draft cases on every feature.
