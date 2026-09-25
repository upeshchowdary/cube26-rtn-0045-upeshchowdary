# F-011 · HttpRetryOptions cannot disable Interactions retries with zero attempts

- **Date:** 2026-09-25
- **Source:** installed `google-genai==2.25.0` source and P5 replay test
- **Status:** handled
- **GitHub issue:** not yet mirrored (issues are not enabled on the fork)

## Finding

`HttpRetryOptions(attempts=0)` is rewritten by the legacy client to one attempt. The Interactions path treats
that field as a retry count, leaving one silent provider retry despite a zero value.

## Impact

A hidden retry can spend another daily-quota request and extend a job lease outside the durable worker's retry
policy.

## Our handling

The client clears `sdk_configuration.retry_config` on both synchronous and asynchronous Interactions resources.
The worker owns retries; the behavior is pinned by `test_sdk_automatic_retries_are_off`.
