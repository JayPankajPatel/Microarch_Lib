// Real macro bodies for elaboration-time checks. Included by ma_assert.svh
// for tools that support IEEE 1800-2017 20.11 elaboration system tasks.

// Checks __prop and issues an elaboration-time $error if it does not hold.
// Must be called directly in a module (or interface) body, not inside a
// procedural block -- see IEEE 1800-2017 20.11, Example 1.
`define MA_ASSERT_INIT(__name, __prop) \
  if (!(__prop)) \
    $error("%s:%0d: [%s] check failed", `__FILE__, `__LINE__, `MA_STRINGIFY(__name));
