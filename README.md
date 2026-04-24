# YK-ComfyUI-HybridI2I-OSS  
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)  
> **YK-ComfyUI-HybridI2I-OSS 全能图片生成节点（支持社区版 / 全能Xinbao / 官方PRO 混合策略）**

本节点提供 **批量图像到图像生成（Image-to-Image）** 能力，支持最多 **10 组任务并行处理**，每组可上传最多 3 张参考图 + 自定义提示词，并自动按 **稳定性优先策略** 调用不同后端 API。

---

## 🚀 核心特性

- ✅ **三重 API 后备策略（自动降级）**：  
  执行顺序固定为：**社区版 → 全能Xinbao → 官方PRO版**  
  （无需手动选择 endpoint，系统自动 fallback）
- ✅ **统一命名规范**：所有界面与参数使用「全能Xinbao」标识
- ✅ **灵活重试控制**：可为每种模式单独设置最大尝试次数（0 = 跳过）
- ✅ **多图床支持**：ImgBB 或 阿里云 OSS（需安装 `oss2`）
- ✅ **批量生成**：每组任务可生成 1~10 个变体
- ✅ **全局并发控制**：避免请求过载
- ✅ **上传 URL 输出**：新增 `上传图片URLs` 端口，可获取每组参考图上传后的图床链接
- ✅ **OSS 日期归档**：阿里云 OSS 自动按 `yyyy-mm-dd` 日期分目录存储

---

## 📦 安装步骤

### 1. 进入 ComfyUI 的 `custom_nodes` 目录

### 2. 克隆本仓库

### 3. （可选）安装阿里云 OSS 支持（如需使用 OSS 图床）

> 💡 如果只使用 ImgBB，无需额外依赖。

### 4. 重启 ComfyUI  
节点将自动加载，名称为：  
**`YK-ComfyUI-HybridI2I-OSS`**

---

## ⚙️ 参数详解

### 🔑 API 密钥（必填其一）

| 参数 | 说明 |
|------|------|
| `runninghub_api_key` | RunningHub 平台 API 密钥（用于 **社区版** 和 **官方PRO版**） |
| `全能Xinbao_api_key` | 全能Xinbao 专用 API 密钥（用于 **全能Xinbao 模式**） |

> ⚠️ **注意**：  
> - 如果启用「社区版」或「官方PRO版」，必须填写 `runninghub_api_key`  
> - 如果启用「全能Xinbao」，必须填写 `全能Xinbao_api_key`

---

### 🔄 执行策略（核心控制）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `社区版_最大尝试次数` | 2 | 设为 `0` 则跳过。**最优先尝试** |
| `全能Xinbao_最大尝试次数` | 1 | 设为 `0` 则跳过。**第二优先** |
| `官方PRO版_最大尝试次数` | 1 | 设为 `0` 则跳过。**最后尝试** |

> ✅ 系统会按 **社区 → 全能Xinbao → 官方PRO** 顺序依次重试，直到成功或耗尽所有尝试次数。

---

### ☁️ 图床配置（用于上传参考图）

| 图床类型 | 必填参数 |
|----------|--------|
| **ImgBB** | `imgbb_api_key` |
| **阿里云 OSS** | `oss_access_key_id`<br>`oss_access_key_secret`<br>`oss_bucket_name`<br>`oss_endpoint`（默认 `oss-cn-beijing.aliyuncs.com`） |

> 💡 推荐新手使用 **ImgBB**（免费、简单）。  
> 使用 OSS 需先安装 `oss2` 库。  
> 📁 OSS 上传路径格式：`yyyy-mm-dd/comfyui_rhart/{timestamp}_{random}.png`，按日期自动归档。

---

### 🖼️ 全局生成参数（适用于所有模式）

| 参数 | 可选项 | 说明 |
|------|--------|------|
| `resolution` | `1K` / `2K` / `4K` / `8K` | 输出分辨率（8K 会映射为 4K） |
| `aspect_ratio` | `1:1`, `2:3`, `3:2`, ..., `自动` | 图像宽高比 |
| `max_wait_time` | 30 ~ 600 秒（默认 **120**） | 单个任务最大等待时间 |
| `global_concurrent_tasks` | 1 ~ 10（默认 3） | 全局最大并发组数 |
| `seed` | 整数 | 当前版本仅用于日志调试，不影响实际生成（各 API 内部随机）|

---

### 📥 输入说明（每组 A~J）

- 每组可连接 **1~3 张参考图**（`image_A_a`, `image_A_b`, `image_A_c`）
- 必须提供 **提示词**（`prompt_1` ~ `prompt_10`）
- 可设置 **每组生成数量**（`batch_count_1` ~ `batch_count_10`，1~10）

> ✅ 至少需要 **1 组有效输入**（有图 + 有提示词）才能运行。

---

### 📤 输出说明

| 输出端口 | 类型 | 说明 |
|----------|------|------|
| `输出_1` ~ `输出_10` | `IMAGE` | 每组生成的图片结果（若失败则返回 64×64 黑图） |
| `所有成功图像` | `IMAGE` | 全部成功图片合并输出 |
| `上传图片URLs` | `STRING` | 每组参考图上传后的图床 URL 列表，格式为 `组1: url1, url2\n组2: url3\n...` |

> 💡 连接 `Show Text` 或 `Save Text` 节点可查看和保存 URL。

---

## ⚠️ 注意事项

1. **API 密钥安全**：不要将密钥提交到公共仓库。
2. **图床选择**：
   - ImgBB 免费但有速率限制
   - 阿里云 OSS 更稳定，适合高频使用
3. **失败处理**：
   - 若所有尝试均失败，对应输出将返回 **64×64 黑图**
   - 详细错误日志会打印在 ComfyUI 控制台（含重试次数、失败原因）
4. **网络要求**：需能访问：
   - `https://www.runninghub.cn`（社区/官方）
   - `https://xinbaoapi.dpdns.org`（全能Xinbao）
5. **OSS 依赖**：使用阿里云 OSS 前务必运行 `pip install oss2`
6. **节点名称**：在 ComfyUI 节点菜单中搜索 **`YK-ComfyUI`** 即可找到

---

## 📄 示例工作流

1. 连接 2 张参考图到 `image_A_a` 和 `image_A_b`
2. 在 `prompt_1` 输入：“赛博朋克风格，夜晚城市”
3. 设置 `batch_count_1 = 3`
4. 填写 `runninghub_api_key` 和 `全能Xinbao_api_key`
5. 保持默认策略（社区尝试 2 次，Xinbao 1 次）
6. 运行 → 节点将输出 3 张符合描述的变体图

---

## 📞 支持与反馈

- 本节点由 **影客AI（YingKe AI）** 团队维护
- 如遇问题，请在 [GitHub Issues](https://github.com/Bzbaozi/Comfyui-YK-runninghub-PRO/issues) 提交
- 欢迎 Star ⭐ 本项目！

---

> Made with ❤️ for ComfyUI users.

## 📄 许可证

本项目采用 [MIT License](LICENSE)，允许自由使用、修改和分发。

详见 [LICENSE](LICENSE) 文件。