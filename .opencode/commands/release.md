执行发布流程：

1. 询问版本类型：patch / minor / major（等待我回答后再继续）
2. 运行 `uv version --bump <type>`，输出新版本号
3. 在 commit 前，运行 `git diff --stat HEAD` 获取改动文件列表，并运行 `git diff HEAD` 了解具体变更内容，然后将所有改动（包括版本升级）一起 commit，commit message 格式如下：
   - 第一行：`bump version to <new_version>`
   - 空行
   - 后续行：用简洁的条目列出本次主要变更（参考 git diff 内容），例如：
     ```
     - fix: <描述具体修复内容>
     - feat: <描述新增功能>
     - refactor: <描述重构内容>
     ```
   命令示例：
   ```
   git add -A && git commit -m "bump version to <new_version>

   - <change 1>
   - <change 2>"
   ```
4. 打 tag 并推送分支和 tag：
```
   git tag -a v<new_version> -m "Release v<new_version>"
   git push origin main
   git push origin v<new_version>
```
5. 汇报完成，显示最终版本号和 tag

$ARGUMENTS 如果提供了（patch/minor/major），跳过第1步直接使用。
```

**使用方式：**
```
/release          # 会询问 patch/minor/major
/release patch    # 直接执行，不询问