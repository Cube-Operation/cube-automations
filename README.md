# cube-automations

Cube Sandbox 的自动化仓库。当前任务：定时从 GitHub API 拉取 [tencentcloud/CubeSandbox](https://github.com/tencentcloud/CubeSandbox) 的贡献者数据，生成 `data/contributors.json`，供文档站**运行时**读取。

文档站页面在浏览器里实时 fetch 本仓库的 raw JSON（带 loading 动画）。`raw.githubusercontent.com` 返回 `Access-Control-Allow-Origin: *`，浏览器跨域可直接读（CNB / Gitee 的 raw 均已实测会被 CORS 拦截）。

本地预览覆盖：`npm run docs:dev` 时若设置了 `CONTRIBUTORS_JSON_PATH`，data loader 会直接读指定的本地 JSON（Node 侧，无 CORS），页面不发起运行时请求。

## 公开 JSON URL

默认地址（文档站 `CONTRIBUTORS_JSON_URL` 对准这里）：

```
https://raw.githubusercontent.com/Cube-Operation/cube-automations/refs/heads/master/data/contributors.json
```

若 GitHub 仓库路径或默认分支不同，改文档站 `docs/.vitepress/contributors-source.js` 里的 URL，并同步改本 README。

## JSON 契约

```json
{
  "generatedAt": "2026-08-17T06:00:00Z",
  "repo": "tencentcloud/CubeSandbox",
  "htmlUrl": "https://github.com/tencentcloud/CubeSandbox",
  "stats": { "contributors": 80, "commits": 1500, "stars": 2000 },
  "activeContributors": [
    {
      "login": "fslongjin",
      "htmlUrl": "https://github.com/fslongjin",
      "avatarUrl": "https://avatars.githubusercontent.com/u/0?v=4",
      "contributions": 123
    }
  ],
  "contributors": [
    {
      "login": "someone",
      "htmlUrl": "https://github.com/someone",
      "avatarUrl": "https://avatars.githubusercontent.com/u/1?v=4",
      "contributions": 3
    }
  ]
}
```

- `stats` 统计全体人类贡献者（活跃 + 其他）
- bot（`type=Bot`、login 以 `[bot]` 结尾、以及 dependabot / github-actions 等）会被去掉
- `activeContributors` 与 `contributors` 均按 `contributions` 降序，且**互不重复**：进入活跃区的人不会再出现在 `contributors` 里

## 活跃贡献者配置

「活跃贡献者」区块由 [`config/active-contributors.yml`](config/active-contributors.yml) 驱动，改这个文件即可，下次流水线运行后生效：

```yaml
threshold: 10        # 贡献数 >= 该值自动进入活跃贡献者（默认 10）
force:               # 强制列入的 GitHub 用户名，即使低于阈值
  - someuser
```

规则：

1. **强制列出**：`force` 里的 login 一定进入活跃区；若此人不在仓库贡献者列表中，会调用 `/users/{login}` 拉取资料，并按 **1 个贡献**计入排序
2. **排序**：活跃区仍按贡献数降序
3. **去重**：活跃区出现的人不会再进入 All Contributors

## 本地运行

需要能访问 `api.github.com`。建议设置 `GITHUB_TOKEN`（Fine-grained：对 `tencentcloud/CubeSandbox` 的 Contents 只读即可），否则匿名额度很容易 403。

```bash
pip install -r requirements.txt
export GITHUB_TOKEN=ghp_xxx
python3 scripts/fetch_contributors.py
```

内容（不含 `generatedAt`）与现有文件相同时不会重写，避免无意义提交。

文档站本地预览可以用这份文件，而不必等 GitHub 上的 JSON 更新：

```bash
cd /path/to/CubeSandbox/docs
CONTRIBUTORS_JSON_PATH=/path/to/cube-automations/data/contributors.json npm run docs:dev
```

## GitHub Actions 流水线

[`.github/workflows/update-contributors.yml`](.github/workflows/update-contributors.yml)：

- 每天 06:00（Asia/Shanghai，cron `0 22 * * *` UTC）定时跑
- `workflow_dispatch` 可在 Actions 页面手动触发
- 用内置 `GITHUB_TOKEN` 调 GitHub API（公开仓库只读，额度足够）并回写 commit
- 无变化则跳过 commit；Actions 的 `GITHUB_TOKEN` 推送默认不会再触发其他 workflow，不会循环构建

### 仓库侧需要你做的

1. 在 GitHub 创建 `Cube-Operation/cube-automations`（或你的目标路径），把本仓库推上去
2. 仓库 Settings → Actions → General → Workflow permissions 设为 **Read and write permissions**（回写 JSON 需要）
3. 手动跑一次 Actions 里的 `update-contributors`，确认 `data/contributors.json` 出现在 `master` 上
4. 若仓库路径/分支不是 `Cube-Operation/cube-automations@master`，同步改文档站的 `CONTRIBUTORS_JSON_URL`
