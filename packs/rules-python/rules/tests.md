---
title: Tests state what should be true, not what the code does
globs: ["tests/**/*.py", "**/test_*.py", "**/*_test.py"]
always: false
---

Name a test after the behaviour it pins down: `test_refund_rejects_negative_amount`,
not `test_refund_2`. The name is what a failure report shows, so it should say
what broke without anyone opening the file.

Assert on outcomes, not on the steps taken to reach them. A test that asserts
which internal methods were called fails whenever the implementation is
refactored, which trains people to update tests without reading them.

Use plain `assert`. Use `pytest.raises` with `match=` so that a differently
caused exception of the same type does not pass silently.

Write the failing test before the fix when fixing a bug. A test that has never
failed has not been shown to detect anything.
