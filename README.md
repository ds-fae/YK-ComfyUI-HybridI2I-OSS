# YK-ComfyUI-HybridI2I-OSS
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
> **纯 URL 工作流 · 批量图生图节点（社区版 / 全能Xinbao / 官方PRO 混合策略）**

本节点为 **纯 URL 工作流设计**：参考图通过 URL 传入，生成结果自动上传至 **阿里云 OSS** 并返回可访问的 URL 列表。支持最多 **10 组任务并行处理**，每组可传入最多 3 张参考图 URL + 自定义提示词，自动按 **稳定性优先策略** 调用不同后端 API。

---

## 核心特性

- **纯 URL 工作流**：参考图直接传入 URL，结果图自动上传 OSS 返回 URL
- **三重 API 后备策略（自动降级）**：执行顺序固定为 **社区版 → 全能Xinbao → 官方PRO版**
- **灵活重试控制**：可为每种模式单独设置最大尝试次数（0 = 跳过）
- **批量生成**：每组任务可生成 1~10 个变体
- **全局并发控制**：避免请求过载
- **OSS 日期归档**：结果图自动按 `yyyy-mm-dd/comfyui_rhart/` 日期分目录存储

---

## 安装步骤

### 1. 进入 ComfyUI 的 `custom_nodes` 目录

### 2. 克隆本仓库

### 3. 安装依赖

```bash
pip install oss2 requests Pillow
```

> 本节点 **必须** 安装 `oss2`，因为结果图只能通过 OSS 上传返回 URL。

### 4. 重启 ComfyUI
节点将自动加载，名称为：**`YK-ComfyUI-HybridI2I-OSS`**

---

## 参数详解

### API 密钥（必填其一）

| 参数 | 说明 |
|------|------|
| `runninghub_api_key` | RunningHub 平台 API 密钥（用于 **社区版** 和 **官方PRO版**） |
| `全能Xinbao_api_key` | 全能Xinbao 专用 API 密钥（用于 **全能Xinbao 模式**） |

> **注意**：
> - 如果启用「社区版」或「官方PRO版」，必须填写 `runninghub_api_key`
> - 如果启用「全能Xinbao」，必须填写 `全能Xinbao_api_key`

---

### 执行策略（核心控制）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `社区版_最大尝试次数` | 2 | 设为 `0` 则跳过。**最优先尝试** |
| `全能Xinbao_最大尝试次数` | 1 | 设为 `0` 则跳过。**第二优先** |
| `官方PRO版_最大尝试次数` | 1 | 设为 `0` 则跳过。**最后尝试** |

> 系统会按 **社区 → 全能Xinbao → 官方PRO** 顺序依次重试，直到成功或耗尽所有尝试次数。

---

### 阿里云 OSS 配置（必填）

结果图必须上传到 OSS 才能获取 URL，以下参数全部必填：

| 参数 | 说明 |
|------|------|
| `oss_access_key_id` | 阿里云 AccessKey ID |
| `oss_access_key_secret` | 阿里云 AccessKey Secret |
| `oss_bucket_name` | OSS Bucket 名称 |
| `oss_endpoint` | OSS Endpoint（默认 `oss-cn-beijing.aliyuncs.com`） |

> OSS 上传路径格式：`yyyy-mm-dd/comfyui_rhart/{timestamp}_{random}.png`，按日期自动归档。

---

### 全局生成参数

| 参数 | 可选项 | 说明 |
|------|--------|------|
| `resolution` | `1K` / `2K` / `4K` / `8K` | 输出分辨率（8K 会映射为 4K） |
| `aspect_ratio` | `1:1`, `2:3`, `3:2`, ..., `自动` | 图像宽高比 |
| `max_wait_time` | 30 ~ 600 秒（默认 **120**） | 单个任务最大等待时间 |
| `global_concurrent_tasks` | 1 ~ 10（默认 3） | 全局最大并发组数 |
| `max_prompt_lines_global` | -1 ~ 50（默认 -1） | 每组最多使用多少行提示词（-1 = 不限制）|
| `seed` | 整数 | 当前版本仅用于日志调试，不影响实际生成 |

---

### 输入说明（每组 A~J）

- **参考图 URL**：每组可传入 **1~3 个图片 URL**（`image_url_A_a` ~ `image_url_J_c`）
- **提示词**：`prompt_1` ~ `prompt_10`，每行一个变体提示词
- **生成数量**：`batch_count_1` ~ `batch_count_10`（当提示词只有 1 行时生效）

> 提示词多行时，行数自动决定生成数量，`batch_count` 被忽略。
> 至少需要 **1 组有效输入**（有 URL + 有提示词）才能运行。

---

### 输出说明

| 输出端口 | 类型 | 说明 |
|----------|------|------|
| `结果图URLs` | `STRING` | 所有生成结果图的 OSS URL，格式为 `组1: url1, url2\n组2: url3\n...` |

> 连接 `Show Text` 或 `Save Text` 节点可查看和保存 URL。

---

## 注意事项

1. **API 密钥安全**：不要将密钥提交到公共仓库。
2. **OSS 必填**：本节点完全依赖 OSS 返回结果，必须正确配置阿里云 OSS。
3. **Bucket 权限**：确保 OSS Bucket 已开启公共读权限，或已配置对应访问策略。
4. **失败处理**：若某变体生成失败，对应组会标记为 `(失败)` 或 `(无)`，详细错误日志打印在 ComfyUI 控制台。
5. **网络要求**：需能访问：
   - `https://www.runninghub.cn`（社区/官方）
   - `https://xinbaoapi.dpdns.org`（全能Xinbao）
6. **节点名称**：在 ComfyUI 节点菜单中搜索 **`YK-ComfyUI`** 即可找到

---

## 示例工作流

1. 在 `image_url_A_a` 输入参考图公开 URL
2. 在 `prompt_1` 输入："赛博朋克风格，夜晚城市"
3. 设置 `batch_count_1 = 3`
4. 填写 `runninghub_api_key`、`全能Xinbao_api_key` 和 OSS 配置
5. 保持默认策略（社区尝试 2 次，Xinbao 1 次）
6. 运行 → 节点将输出 3 张结果图的 OSS URL

---

## 支持与反馈

- 本节点由 **影客AI（YingKe AI）** 团队维护
- 如遇问题，请在 [GitHub Issues](https://github.com/ds-fae/YK-ComfyUI-HybridI2I-OSS/issues) 提交
- 欢迎 Star 本项目！

---

## 许可证

本项目采用 [MIT License](LICENSE)，允许自由使用、修改和分发。
