# YK-ComfyUI-HybridI2I-OSS

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

> **批量图生图节点 · 多API混合策略 · 结果图OSS上传 · 回调通知**

支持最多 **10 组任务并行处理**，每组可传入最多 3 张参考图 + 自定义提示词，自动按固定策略调用不同后端 API（社区版 → 全能Xinbao → 官方PRO版），结果图上传阿里云 OSS，全部完成后统一 POST 回调通知。

---

## 核心特性

- **三重 API 后备策略（自动降级）**：社区版 → 全能Xinbao → 官方PRO版
- **灵活重试控制**：每种模式可独立设置最大尝试次数（0 = 跳过）
- **批量生成**：每组最多 10 个变体，支持多行提示词自动拆分
- **全局并发控制**：限制同时处理的组数，避免请求过载
- **结果图 OSS 上传**：自动按 `yyyy-mm-dd/comfyui_rhart/{timestamp}_{random}.png` 日期分目录存储
- **回调通知**：全部组执行完毕后，统一 POST 所有 OSS 路径到指定 `callback_url`
- **双图床支持**：参考图上传支持 ImgBB 和阿里云 OSS 两种方式

---

## 安装

### 方式一：ComfyUI Registry（推荐）

在 ComfyUI Manager 中搜索 `YK-ComfyUI-HybridI2I-OSS` 安装。

### 方式二：手动安装

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/ds-fae/YK-ComfyUI-HybridI2I-OSS.git
pip install oss2 requests Pillow
```

重启 ComfyUI 后，节点自动加载。

---

## 参数说明

### 执行策略

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `社区版_最大尝试次数` | 2 | 设为 0 则跳过，**最优先** |
| `全能Xinbao_最大尝试次数` | 1 | 设为 0 则跳过，**第二优先** |
| `官方PRO版_最大尝试次数` | 1 | 设为 0 则跳过，**最后尝试** |

### API 密钥

| 参数 | 说明 |
|------|------|
| `runninghub_api_key` | RunningHub 平台密钥（社区版 + 官方PRO版） |
| `全能Xinbao_api_key` | 全能Xinbao 专用密钥 |

### 图床配置

| 参数 | 说明 |
|------|------|
| `image_hosting` | 参考图上传方式：`ImgBB` 或 `阿里云 OSS` |
| `imgbb_api_key` | ImgBB API 密钥（选择 ImgBB 时必填） |
| `oss_access_key_id` | 阿里云 AccessKey ID |
| `oss_access_key_secret` | 阿里云 AccessKey Secret |
| `oss_bucket_name` | OSS Bucket 名称 |
| `oss_endpoint` | OSS Endpoint（默认 `oss-cn-beijing.aliyuncs.com`） |

### 全局参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `resolution` | 1K | 输出分辨率：1K / 2K / 4K / 8K |
| `aspect_ratio` | 自动 | 图像宽高比 |
| `max_wait_time` | 120s | 单任务最大等待时间（30~600秒） |
| `global_concurrent_tasks` | 3 | 最大并发组数（1~10） |
| `max_prompt_lines_global` | -1 | 每组最多提示词行数（-1=不限） |
| `seed` | 0 | 随机种子 |
| `callback_url` | 空 | 全部完成后 POST 回调 URL（可选） |

### 输入（每组 A~J）

- **参考图**：`image_A_a` / `image_A_b` / `image_A_c`（IMAGE 类型，每组最多 3 张）
- **提示词**：`prompt_1` ~ `prompt_10`（多行时自动拆分为多变体）
- **生成数量**：`batch_count_1` ~ `batch_count_10`（仅单行提示词时生效）

### 输出

| 输出端口 | 类型 | 说明 |
|----------|------|------|
| `输出_1` ~ `输出_10` | IMAGE | 各组生成的图像 |
| `所有成功图像` | IMAGE | 所有组成功图像合并 |
| `上传图片URLs` | STRING | 参考图上传后的 URL 汇总 |

---

## 回调说明

当 `callback_url` 不为空时，所有组执行完毕后会统一 POST：

```json
{
  "paths": [
    "2026-04-24/comfyui_rhart/1714012345678_abc12345.png",
    "2026-04-24/comfyui_rhart/1714012345999_xyz98765.png"
  ]
}
```

回调 URL 示例：
```
https://api.lezai-ai.cn/api/v1/task-upload?task_id=xxx&token=yyy
```

---

## 注意事项

1. **OSS 配置**：结果图上传 OSS 需完整配置 AK/SK/Bucket/Endpoint
2. **Bucket 权限**：确保 OSS Bucket 已开启公共读权限
3. **API 密钥安全**：不要将密钥提交到公共仓库
4. **网络要求**：需能访问 `runninghub.cn` 和 `xinbaoapi.dpdns.org`
5. **失败处理**：失败的组输出 64×64 占位图像，详细日志在 ComfyUI 控制台

---

## 许可证

[MIT License](LICENSE)
