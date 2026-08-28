# Release 发布规范

本仓库从现在起统一使用 **GitHub Releases** 记录正式版本。

## 强制规则

- 以后每次形成新的可用版本、功能更新或修复更新，都必须同步发布一个新的 GitHub Release。
- 不允许只 `commit` / `push` 更新代码而长期不发布 Release。
- 每个 Release 必须对应明确的版本标签，建议使用语义化版本：`v主版本.次版本.修订版本`，例如 `v0.1.0`、`v0.1.1`、`v1.0.0`。
- Release Notes 至少写明：本次新增内容、修复内容、重要变化和已知问题（如有）。
- 仅有很小的文档或拼写修改时，可以不单独发布，但必须在下一个 Release Notes 中记录。

## 推荐发布流程

1. 完成代码修改并自测。
2. Commit 并 Push 到默认分支。
3. 更新版本号。
4. 创建对应 Git Tag。
5. 在 GitHub Releases 中发布新版本并填写 Release Notes。

> 规则：**以后正式更新都要发布 Releases。**
