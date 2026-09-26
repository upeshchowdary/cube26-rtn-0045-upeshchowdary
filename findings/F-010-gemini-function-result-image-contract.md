# F-010 · Gemini function results can carry images and input forms are exclusive

- **Date:** 2026-09-25
- **Source:** installed `google-genai==2.25.0` source during the §0.7 verification spike
- **Status:** handled in the P5 session loop
- **GitHub issue:** not yet mirrored (issues are not enabled on the fork)

## Finding

The prompt says function results cannot carry images and implies that contents and steps may be mixed. The
installed Gemini SDK instead permits image content inside a `function_result`, and an interaction input is either
a contents list or a steps list, never a mixture.

## Impact

Putting crop bytes outside the function result, or mixing input representations, would produce an invalid or
ambiguous continuation request.

## Our handling

Crop responses are returned inside the corresponding `function_result`. Continuations use a steps list chained
only with `previous_interaction_id`; the initial request uses contents. This behavior is covered by replay tests.
