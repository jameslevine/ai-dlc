---
title: Prefer immutable types and explicit absence
globs: ["**/*.java", "**/*.kt"]
always: false
---

Model data with records in Java and data classes in Kotlin. Make fields final,
and return unmodifiable collections from accessors rather than the backing
collection itself.

Express absence in the type. Use `Optional<T>` as a return type in Java, and
Kotlin's nullable types with the safe-call operator. Do not use `Optional` for
fields or parameters; it was not designed for that and costs an allocation on a
hot path.

Never swallow an exception. Catching one and logging nothing leaves a failure
with no evidence, which is the hardest kind to diagnose. Either handle it
meaningfully or let it propagate, and when you wrap it, pass the original as the
cause.

Keep `equals`, `hashCode` and `toString` consistent with each other. A record or
data class gives you all three correctly; a hand-written pair that disagrees
breaks every hash-based collection silently.
