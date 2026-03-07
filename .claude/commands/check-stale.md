---
name: check-stale
description: Analyze a code scope for stale/dead code, automatically tracing related files
argument-hint: <file or directory path> [-- additional instructions]
allowed-tools: Read, Glob, Grep, Bash
---

Parse the user input from: $ARGUMENTS

## Parse Input

Split $ARGUMENTS by the first occurrence of ` -- `:
- **Left part** → the file/directory scope to analyze
- **Right part** → additional instructions from the user (may be empty)

If no ` -- ` is found, treat the entire input as the scope and additional instructions as empty.

## Step 1: Resolve the Scope
...（后续内容不变）...

## Step 6: Apply Additional Instructions

If additional instructions were provided, apply them on top of the standard analysis.
Examples of what users might specify:
- Focus area: "重点检查 v1 相关的遗留代码"
- Exclusions: "ignore test files"
- Extra context: "funding_rate_v2 已经上线，v1 可以全部删除"

Incorporate these instructions throughout the analysis — they may affect confidence levels, scope, or what counts as stale.
```

**使用方式：**
```
/check-stale src/strategy/ -- funding_rate_v1 已被 v2 替代，可以大胆标 High confidence
/check-stale src/execution/order_manager.py -- ignore anything under the legacy/ subfolder