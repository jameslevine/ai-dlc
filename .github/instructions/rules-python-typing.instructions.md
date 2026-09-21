---
applyTo: "**/*.py"
---

# Annotate at the boundaries and keep the type checker clean

Annotate every function signature and every dataclass or model field. Local
variables need annotations only where inference genuinely fails.

Use modern syntax: `list[str]` and `str | None`, not `List[str]` and
`Optional[str]`.

Fix type errors rather than silencing them. When a suppression is genuinely
required, make it specific and explain it on the same line:

```python
value = untyped_library.get()  # type: ignore[no-any-return]  # library ships no stubs
```

A bare `# type: ignore` hides the next error too, which is how a suppression
added for one reason ends up masking a real bug.
