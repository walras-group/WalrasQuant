执行发布流程：

1. 询问版本类型：patch / minor / major（等待我回答后再继续）
2. 检查是否有未提交的改动（`git status`），如果有，先执行：`git add -A && git commit -m "chore: pre-release cleanup"`
3. 运行 `uv version --bump <type>`，输出新版本号
4. 将版本改动 commit：`git add pyproject.toml uv.lock && git commit -m "bump version to <new_version>"`
5. 打 tag 并推送：
```
   git tag -a v<new_version> -m "Release v<new_version>"
   git push origin v<new_version>
```
6. 汇报完成，显示最终版本号和 tag

$ARGUMENTS 如果提供了（patch/minor/major），跳过第1步直接使用。
```

**使用方式：**
```
/release          # 会询问 patch/minor/major
/release patch    # 直接执行，不询问