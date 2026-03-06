# /api-migrate

根据用户提供的 API 变更文档，扫描当前代码库中所有受影响的调用点，并自动完成迁移更新。

## 用法

```
/api-migrate <文档路径>
/api-migrate <文档路径> --dry-run
```

**参数说明：**
- `<文档路径>`：API changelog / migration guide / diff 文件的路径（必填），由 `$ARGUMENTS` 传入
- `--dry-run`：只列出变更点，不实际修改文件

---

## 执行步骤

你将收到一个参数：`$ARGUMENTS`

### Step 1：读取变更文档

解析 `$ARGUMENTS`，提取文档路径（以及是否有 `--dry-run` 标志）。

读取该文档，从中提取所有 API 变更项，结构化为以下格式：

```
变更类型 | 旧写法 | 新写法 | 说明
```

变更类型包括：
- `rename`：函数/方法/类名重命名
- `param_change`：参数新增 / 删除 / 重命名 / 类型变更
- `deprecated`：废弃字段或方法
- `signature`：函数签名结构调整
- `import`：导入路径变更
- `breaking`：其他 breaking change

输出解析结果摘要，让用户确认理解是否正确，再进入下一步。

---

### Step 2：扫描代码库

根据解析出的变更项，在当前代码库中搜索所有受影响的调用点。

**搜索策略：**
- 优先使用 `grep -rn` 或 `rg`（ripgrep）进行关键词搜索
- 对每个变更项，搜索旧的函数名、方法名、参数名、导入路径等
- 过滤掉 `.git/`、`node_modules/`、`__pycache__/`、`dist/`、`target/` 等无关目录
- 记录每个命中的文件路径和行号

输出扫描结果：
```
找到 N 处需要更新，涉及 M 个文件：
- src/trading/order.py (3 处)
- src/exchange/binance.py (1 处)
...
```

---

### Step 3：执行迁移

如果带有 `--dry-run`，只输出每处变更的 diff 预览，不修改文件。

否则，对每个命中点执行精确替换：
- 使用文件读取 + 字符串替换，不做模糊修改
- 每次修改后验证语法（Python 用 `python -m py_compile`，Rust 用 `cargo check`，JS/TS 用 `tsc --noEmit`）
- 如果某处变更语义复杂（无法安全自动替换），标记为 `⚠️ 需人工确认` 并跳过

---

### Step 4：输出迁移报告

```
✅ 自动迁移完成

已更新：
- src/trading/order.py:42   rename: get_funding_rate → fetch_funding_rate
- src/trading/order.py:87   param_change: symbol= → instrument_id=
- src/exchange/binance.py:15 import: from binance.client → from binance.spot

⚠️ 需人工确认（1 处）：
- src/legacy/old_api.py:203  breaking: 返回值结构变更，自动替换风险高，请手动检查

建议：运行测试套件以验证迁移结果。
```

---

## 注意事项

- 始终优先保证安全性，宁可标记为人工确认也不要做破坏性的盲目替换
- 变更文档可能是 Markdown、纯文本、JSON diff 或 GitHub Release Notes 格式，灵活解析
- 若代码库包含多种语言，分语言处理
- 迁移前建议用户先 `git commit` 当前状态作为回滚点