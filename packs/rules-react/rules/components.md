---
title: Components render; hooks hold the logic
globs: ["**/*.tsx", "**/*.jsx"]
always: false
---

Keep a component's body close to a description of what it renders. When branching
and data manipulation start to dominate, move them into a custom hook or a plain
function and call it.

Derive during render rather than storing derived values in state. A `useState`
holding something computable from props is a second source of truth, and keeping
it in step is what the bug will be.

Reach for an effect only to synchronise with something outside React: a
subscription, a timer, an imperative DOM API. Fetching, transforming and
responding to a prop change usually have a better home. An effect whose only job
is to call `setState` from other state is almost always the derived-value mistake
wearing a different hat.

Give every list item a key that comes from the data. An array index reuses a key
when the list reorders, so React keeps the wrong element's state.
