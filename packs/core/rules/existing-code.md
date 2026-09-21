---
title: Match the code that is already here
always: true
---

Read neighbouring code before writing new code. Follow the conventions you find
there over the conventions you prefer: naming, error handling, module layout,
test style.

Reuse what exists rather than adding a parallel implementation. If a helper
does almost what you need, extend it or call it; a second near-identical
function is a maintenance cost that compounds.

Do not add a dependency when the standard library covers the need. When a
dependency is genuinely warranted, say why in the commit message.
