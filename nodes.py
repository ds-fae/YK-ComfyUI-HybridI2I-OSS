import os
import requests
import time
import random
from PIL import Image
import numpy as np
import torch
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64

# 尝试导入 oss2（按需）
OSS_AVAILABLE = False
try:
    import oss2
    OSS_AVAILABLE = True
except ImportError:
    pass

class YKHybridI2IOSSNode:
    @classmethod
    def INPUT_TYPES(s):
        optional_inputs = {}
        for i in range(10):  # A to J
            group_letter = chr(ord('A') + i)
            optional_inputs[f"image_{group_letter}_a"] = ("IMAGE", {})
            optional_inputs[f"image_{group_letter}_b"] = ("IMAGE", {})
            optional_inputs[f"image_{group_letter}_c"] = ("IMAGE", {})
            optional_inputs[f"prompt_{i+1}"] = ("STRING", {"forceInput": True})
            optional_inputs[f"batch_count_{i+1}"] = ("INT", {
                "default": 1,
                "min": 1,
                "max": 10,
                "step": 1,
                "display": "number"
            })

        return {
            "required": {
                # === 各模式最大尝试次数（核心控制）===
                "社区版_最大尝试次数": ("INT", {
                    "default": 2,
                    "min": 0,
                    "max": 5,
                    "step": 1,
                    "tooltip": "设为0则跳过该模式。执行顺序：第1位（最优先）"
                }),
                "全能Xinbao_最大尝试次数": ("INT", {
                    "default": 1,
                    "min": 0,
                    "max": 5,
                    "step": 1,
                    "tooltip": "设为0则跳过该模式。执行顺序：第2位"
                }),
                "官方PRO版_最大尝试次数": ("INT", {
                    "default": 1,
                    "min": 0,
                    "max": 5,
                    "step": 1,
                    "tooltip": "设为0则跳过该模式。执行顺序：第3位（最后）"
                }),

                # === API 密钥（命名统一）===
                "runninghub_api_key": ("STRING", {"default": "", "placeholder": "RunningHub API 密钥"}),
                "全能Xinbao_api_key": ("STRING", {"default": "", "placeholder": "全能Xinbao API 密钥"}),

                # === 全局参数（所有模式通用）===
                "image_hosting": (["ImgBB", "阿里云 OSS"], {"default": "ImgBB"}),
                "imgbb_api_key": ("STRING", {"default": "", "placeholder": "ImgBB API 密钥"}),
                "oss_access_key_id": ("STRING", {"default": "", "placeholder": "阿里云 AccessKey ID"}),
                "oss_access_key_secret": ("STRING", {"default": "", "placeholder": "阿里云 AccessKey Secret"}),
                "oss_bucket_name": ("STRING", {"default": "", "placeholder": "OSS Bucket 名称"}),
                "oss_endpoint": ("STRING", {"default": "oss-cn-beijing.aliyuncs.com", "placeholder": "OSS Endpoint"}),
                "resolution": (["1K", "2K", "4K", "8K"], {"default": "1K"}),
                "aspect_ratio": (["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "16:9", "9:16", "21:9", "自动"], {"default": "自动"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "global_concurrent_tasks": ("INT", {
                    "default": 3,
                    "min": 1,
                    "max": 10,
                    "step": 1,
                    "tooltip": "全局最大处理组数（仅处理前 N 个有效组，1～10）"
                }),
                "max_wait_time": ("INT", {
                    "default": 120,
                    "min": 30,
                    "max": 600,
                    "step": 30,
                    "tooltip": "每个子任务最大等待时间（秒），适用于所有API模式"
                }),
                # 👇【关键】全局提示词行数限制 —— 放在最后，UI 显示在底部 👇
                "max_prompt_lines_global": ("INT", {
                    "default": -1,
                    "min": -1,
                    "max": 50,
                    "step": 1,
                    "tooltip": "【全局】每组最多使用多少行提示词（-1 = 不限制）。例如设为5，则即使提示词有10行，每组也只生成前5个变体。此参数位于底部便于批量调试。"
                }),
            },
            "optional": optional_inputs
        }

    RETURN_TYPES = ("IMAGE",) * 10 + ("IMAGE",) + ("STRING",) + ("STRING",)
    RETURN_NAMES = tuple(f"输出_{i}" for i in range(1, 11)) + ("所有成功图像", "参考图URLs", "结果图URLs")
    FUNCTION = "generate"
    CATEGORY = "YK-ComfyUI"

    # --- 工具方法 ---
    def tensor_to_pil(self, tensor):
        if tensor.ndim == 4:
            tensor = tensor.squeeze(0)
        i = 255. * tensor.cpu().numpy()
        img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
        return img

    def pil_to_tensor(self, pil_img):
        img_array = np.array(pil_img).astype(np.float32) / 255.0
        return torch.from_numpy(img_array)[None,]

    def upload_to_imgbb(self, pil_img, imgbb_api_key):
        if not imgbb_api_key.strip():
            raise ValueError("请填写 ImgBB API 密钥")
        buf = BytesIO()
        pil_img.save(buf, format="PNG")
        buf.seek(0)
        response = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": imgbb_api_key.strip()},
            files={"image": buf.read()},
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        if result.get("success"):
            return result["data"]["url"]
        else:
            error_msg = result.get("error", {}).get("message", "未知上传错误")
            raise RuntimeError(f"ImgBB 上传失败: {error_msg}")

    def upload_to_aliyun_oss(self, pil_img, access_key_id, access_key_secret, bucket_name, endpoint):
        if not OSS_AVAILABLE:
            raise RuntimeError("未安装 oss2 库，请运行: pip install oss2")
        if not all([access_key_id.strip(), access_key_secret.strip(), bucket_name.strip()]):
            raise ValueError("请填写完整的阿里云 OSS 配置信息")

        date_str = time.strftime("%Y-%m-%d", time.localtime())
        timestamp = str(int(time.time() * 1000))
        random_suffix = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8))
        object_key = f"{date_str}/comfyui_rhart/{timestamp}_{random_suffix}.png"

        auth = oss2.Auth(access_key_id.strip(), access_key_secret.strip())
        bucket = oss2.Bucket(auth, f'https://{endpoint.strip()}', bucket_name.strip())

        buf = BytesIO()
        pil_img.save(buf, format="PNG")
        buf.seek(0)

        try:
            bucket.put_object(object_key, buf.getvalue(), headers={'Content-Type': 'image/png'})
        except Exception as e:
            raise RuntimeError(f"阿里云 OSS 上传失败: {e}")

        return f"https://{bucket_name.strip()}.{endpoint.strip()}/{object_key}"

    def upload_image(self, pil_img, image_hosting, **creds):
        if image_hosting == "ImgBB":
            return self.upload_to_imgbb(pil_img, creds.get("imgbb_api_key", ""))
        elif image_hosting == "阿里云 OSS":
            if not OSS_AVAILABLE:
                raise RuntimeError("请选择 ImgBB，或安装 oss2 库以使用阿里云 OSS")
            return self.upload_to_aliyun_oss(
                pil_img,
                creds.get("oss_access_key_id", ""),
                creds.get("oss_access_key_secret", ""),
                creds.get("oss_bucket_name", ""),
                creds.get("oss_endpoint", "")
            )
        else:
            raise ValueError(f"不支持的图床: {image_hosting}")

    # ====== 全能Xinbao 图像生成 ======
    def process_single_variation_banana(self, group_id, var_id, image_urls, prompt, seed,
                                       banana_api_key, model, resolution, aspect_ratio, max_wait_time):
        base_url = "https://xinbaoapi.dpdns.org"
        headers = {
            "Authorization": f"Bearer {banana_api_key.strip()}",
            "Content-Type": "application/json"
        }

        parts = [{"text": prompt}]
        for url in image_urls[:5]:
            parts.append({
                "inlineData": {
                    "mimeType": "image/jpeg",
                    "data": url
                }
            })

        image_config = {}
        if resolution in ["1K", "2K", "4K", "8K"]:
            api_res = "4K" if resolution == "8K" else resolution
            image_config["imageSize"] = api_res
        if aspect_ratio != "自动":
            image_config["aspectRatio"] = aspect_ratio

        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "output": "url",
                **({"topP": 0.95} if seed is not None else {}),
                **({"imageConfig": image_config} if image_config else {})
            }
        }

        print(f"[DEBUG] [组 {group_id} 变体 {var_id}] 发送 全能Xinbao 请求 (model=gemini-3-pro-image-preview, timeout=120s)", flush=True)
        resp = requests.post(
            f"{base_url}/v1beta/models/gemini-3-pro-image-preview:generateContent",
            json=payload,
            headers=headers,
            timeout=120
        )
        resp.raise_for_status()
        data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"[组 {group_id} 变体 {var_id}] 全能Xinbao 无候选结果")

        parts_out = candidates[0].get("content", {}).get("parts", [])
        output_pil = None
        for part in parts_out:
            inline = part.get("inlineData", {})
            mime_type = inline.get("mimeType", "")
            img_data = inline.get("data", "")
            if mime_type.startswith("image/") and isinstance(img_data, str):
                try:
                    if img_data.startswith("http"):
                        img_resp = requests.get(img_data, timeout=30)
                        img_resp.raise_for_status()
                        output_pil = Image.open(BytesIO(img_resp.content)).convert("RGB")
                    else:
                        image_bytes = base64.b64decode(img_data)
                        output_pil = Image.open(BytesIO(image_bytes)).convert("RGB")
                    break
                except Exception as e:
                    continue

        if output_pil is None:
            raise RuntimeError(f"[组 {group_id} 变体 {var_id}] 全能Xinbao 未返回可解析图片")
        return output_pil

    # ====== RunningHub 方法 ======
    def _get_endpoint_paths(self, mode):
        if mode == "official":
            return "/openapi/v2/rhart-image-n-pro-official/edit"
        else:
            return "/openapi/v2/rhart-image-n-pro/edit"

    def process_single_variation_runninghub(self, group_id, var_id, image_urls, prompt, seed,
                                           api_key, resolution, aspect_ratio, max_wait_time, endpoint_path):
        base_url = "https://www.runninghub.cn"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        status_headers = {"Content-Type": "application/json"}
        poll_interval = 3
        max_attempts = min(max_wait_time, 600) // poll_interval or 1

        api_resolution = "4K" if resolution == "8K" else resolution
        submit_payload = {"prompt": prompt, "imageUrls": image_urls, "resolution": api_resolution.lower()}
        if aspect_ratio != "自动":
            ar_map = {"1:1":"1:1","2:3":"2:3","3:2":"3:2","3:4":"3:4","4:3":"4:3","4:5":"4:5","5:4":"5:4","16:9":"16:9","9:16":"9:16","21:9":"21:9"}
            submit_payload["aspectRatio"] = ar_map.get(aspect_ratio, "auto")

        submit_resp = requests.post(f"{base_url}{endpoint_path}", json=submit_payload, headers=headers, timeout=30)
        submit_resp.raise_for_status()
        task_id = submit_resp.json().get("taskId")
        if not task_id:
            raise RuntimeError(f"[组 {group_id} 变体 {var_id}] 未返回 taskId")

        status_payload = {"apiKey": api_key, "taskId": task_id}
        for attempt in range(1, max_attempts + 1):
            time.sleep(poll_interval)
            try:
                resp = requests.post(f"{base_url}/task/openapi/status", json=status_payload, headers=status_headers, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") == 0 and data.get("data") == "SUCCESS":
                    break
                elif data.get("data") == "FAILED":
                    raise RuntimeError("任务失败")
            except:
                pass
        else:
            raise RuntimeError(f"超时（>{max_wait_time}秒）")

        outputs_resp = requests.post(f"{base_url}/task/openapi/outputs", json=status_payload, headers=status_headers, timeout=30)
        outputs_resp.raise_for_status()
        file_url = outputs_resp.json().get("data", [{}])[0].get("fileUrl")
        if not file_url:
            raise RuntimeError("无输出图 URL")

        img_resp = requests.get(file_url, timeout=30)
        img_resp.raise_for_status()
        return Image.open(BytesIO(img_resp.content)).convert("RGB")

    # ====== 核心：多策略尝试引擎（固定顺序）======
    def _build_strategy_from_attempts(self, community_tries, xinbao_tries, official_tries):
        strategy = []
        if community_tries > 0:
            strategy.append({"type": "community", "max_retries": community_tries})
        if xinbao_tries > 0:
            strategy.append({"type": "xinbao", "max_retries": xinbao_tries})
        if official_tries > 0:
            strategy.append({"type": "official", "max_retries": official_tries})
        if not strategy:
            raise ValueError("所有模式的尝试次数均为0，请至少启用一个模式（将某个尝试次数设为 ≥1）")
        return strategy

    def _attempt_with_strategy(self, group_id, var_id, image_urls, prompt,
                              runninghub_api_key, banana_api_key,
                              resolution, aspect_ratio, max_wait_time,
                              strategy):
        total_attempt = 0
        for step in strategy:
            api_type = step["type"]
            max_retries = step["max_retries"]
            for retry in range(max_retries):
                total_attempt += 1
                seed = random.randint(0, 0xffffffff)
                try:
                    if api_type == "community":
                        print(f"[组 {group_id} 变体 {var_id}] 尝试 #{total_attempt} 使用 社区版 (seed={seed})", flush=True)
                        img = self.process_single_variation_runninghub(
                            group_id, var_id, image_urls, prompt, seed,
                            runninghub_api_key,
                            resolution, aspect_ratio, max_wait_time,
                            self._get_endpoint_paths("community")
                        )
                    elif api_type == "official":
                        print(f"[组 {group_id} 变体 {var_id}] 尝试 #{total_attempt} 使用 官方PRO版 (seed={seed})", flush=True)
                        img = self.process_single_variation_runninghub(
                            group_id, var_id, image_urls, prompt, seed,
                            runninghub_api_key,
                            resolution, aspect_ratio, max_wait_time,
                            self._get_endpoint_paths("official")
                        )
                    elif api_type == "xinbao":
                        print(f"[组 {group_id} 变体 {var_id}] 尝试 #{total_attempt} 使用 全能Xinbao (seed={seed})", flush=True)
                        img = self.process_single_variation_banana(
                            group_id, var_id, image_urls, prompt, seed,
                            banana_api_key,
                            "gemini-3-pro-image-preview",
                            resolution, aspect_ratio, max_wait_time
                        )
                    print(f"[组 {group_id} 变体 {var_id}] 成功 ✅", flush=True)
                    return img
                except Exception as e:
                    wait_sec = min(2 ** retry, 10)
                    print(f"⚠️ [组 {group_id} 变体 {var_id}] {api_type} 第 {retry+1} 次失败: {e}", flush=True)
                    if total_attempt < sum(s["max_retries"] for s in strategy):
                        print(f"   → {wait_sec} 秒后重试...", flush=True)
                        time.sleep(wait_sec)
        print(f"❌ [组 {group_id} 变体 {var_id}] 所有 {total_attempt} 次尝试均失败", flush=True)
        return None

    def process_single_group_with_batch(self, group_id, image_tensors, prompt_list, batch_count,
                                       runninghub_api_key, banana_api_key,
                                       image_hosting, creds,
                                       resolution, aspect_ratio, max_wait_time,
                                       strategy):
        image_urls = []
        hosting_name = "ImgBB" if image_hosting == "ImgBB" else "阿里云 OSS"
        print(f"[组 {group_id}] 正在上传 {len(image_tensors)} 张参考图到 {hosting_name}...", flush=True)
        for idx, tensor in enumerate(image_tensors[:5], 1):
            try:
                pil_img = self.tensor_to_pil(tensor)
                url = self.upload_image(pil_img, image_hosting, **creds)
                image_urls.append(url)
                print(f"[组 {group_id}] 参考图 {idx} 上传成功: {url}", flush=True)
            except Exception as e:
                print(f"[组 {group_id}] 跳过无效图像 {idx}: {e}", flush=True)
                continue

        if not image_urls:
            raise RuntimeError(f"[组 {group_id}] 无有效参考图可上传")

        print(f"[组 {group_id}] 参考图全部上传完成，开始生成 {batch_count} 个变体", flush=True)

        successful_tensors = []
        successful_pils = []
        with ThreadPoolExecutor(max_workers=batch_count) as executor:
            futures = [
                executor.submit(
                    self._attempt_with_strategy,
                    group_id, var_index + 1, image_urls,
                    prompt_list[min(var_index, len(prompt_list) - 1)],
                    runninghub_api_key, banana_api_key,
                    resolution, aspect_ratio, max_wait_time,
                    strategy
                )
                for var_index in range(batch_count)
            ]
            for future in futures:
                try:
                    result = future.result()
                    if result is not None:
                        successful_pils.append(result)
                        successful_tensors.append(self.pil_to_tensor(result))
                except Exception as e:
                    print(f"⚠️ [组 {group_id}] 某变体执行异常（已跳过）: {e}", flush=True)

        if not successful_tensors:
            print(f"[组 {group_id}] 所有变体均失败", flush=True)
            return torch.zeros((1, 64, 64, 3), dtype=torch.float32), [], image_urls

        # 上传结果图到图床
        result_image_urls = []
        for idx, pil_img in enumerate(successful_pils, 1):
            try:
                url = self.upload_image(pil_img, image_hosting, **creds)
                result_image_urls.append(url)
                print(f"[组 {group_id}] 结果图 {idx} 上传成功: {url}", flush=True)
            except Exception as e:
                print(f"[组 {group_id}] 结果图 {idx} 上传失败: {e}", flush=True)
                continue

        # 统一尺寸以避免拼接失败（仅针对输出图）
        try:
            first_tensor = successful_tensors[0]
            _, H, W, C = first_tensor.shape
            aligned_tensors = [first_tensor]
            for i in range(1, len(successful_tensors)):
                t = successful_tensors[i]
                if t.shape[1:] != (H, W, C):
                    pil_img = self.tensor_to_pil(t)
                    resized_pil = pil_img.resize((W, H), Image.LANCZOS)
                    t = self.pil_to_tensor(resized_pil)
                aligned_tensors.append(t)
            final_output = torch.cat(aligned_tensors, dim=0)
            print(f"[组 {group_id}] 成功生成并合并 {len(aligned_tensors)} / {batch_count} 个变体", flush=True)
            return final_output, result_image_urls, image_urls
        except Exception as e:
            print(f"❌ [组 {group_id}] 合并成功图像时出错，返回单张: {e}", flush=True)
            return successful_tensors[0], result_image_urls, image_urls

    def generate(self,
                 社区版_最大尝试次数,
                 全能Xinbao_最大尝试次数,
                 官方PRO版_最大尝试次数,
                 runninghub_api_key, 全能Xinbao_api_key,
                 image_hosting,
                 imgbb_api_key,
                 oss_access_key_id, oss_access_key_secret, oss_bucket_name, oss_endpoint,
                 resolution, aspect_ratio, seed, global_concurrent_tasks, max_wait_time,
                 max_prompt_lines_global,
                 **kwargs):

        strategy = self._build_strategy_from_attempts(
            int(社区版_最大尝试次数),
            int(全能Xinbao_最大尝试次数),
            int(官方PRO版_最大尝试次数)
        )

        need_runninghub = any(step["type"] in ["community", "official"] for step in strategy)
        need_xinbao = any(step["type"] == "xinbao" for step in strategy)

        if need_runninghub and not runninghub_api_key.strip():
            raise ValueError("当前策略需要 RunningHub API 密钥，请填写")
        if need_xinbao and not 全能Xinbao_api_key.strip():
            raise ValueError("当前策略包含「全能Xinbao」，请填写其 API 密钥")

        creds = {
            "imgbb_api_key": imgbb_api_key,
            "oss_access_key_id": oss_access_key_id,
            "oss_access_key_secret": oss_access_key_secret,
            "oss_bucket_name": oss_bucket_name,
            "oss_endpoint": oss_endpoint,
        }

        if image_hosting == "ImgBB":
            if not imgbb_api_key.strip():
                raise ValueError("图床选择 ImgBB 时，请填写 API 密钥")
        elif image_hosting == "阿里云 OSS":
            if not OSS_AVAILABLE:
                raise ValueError("请安装 oss2: pip install oss2")
            if not all([oss_access_key_id.strip(), oss_access_key_secret.strip(), oss_bucket_name.strip()]):
                raise ValueError("请填写完整的阿里云 OSS 配置")

        global_concurrent_tasks = min(max(1, int(global_concurrent_tasks)), 10)
        max_wait_time = min(max(30, int(max_wait_time)), 600)
        
        max_prompt_lines_global = int(max_prompt_lines_global)
        if max_prompt_lines_global == 0:
            max_prompt_lines_global = -1

        skipped_placeholder = torch.zeros((1, 1, 1, 3), dtype=torch.float32)
        results = [skipped_placeholder] * 10

        valid_tasks = []
        for i in range(1, 11):
            raw_prompt = kwargs.get(f"prompt_{i}", "")
            prompt_lines = [line.strip() for line in raw_prompt.split('\n') if line.strip()]
            if not prompt_lines:
                continue

            if max_prompt_lines_global > 0 and len(prompt_lines) > max_prompt_lines_global:
                original_len = len(prompt_lines)
                prompt_lines = prompt_lines[:max_prompt_lines_global]
                print(f"[组 {i}] 提示词行数被全局限制为 {len(prompt_lines)} 行（max_prompt_lines_global={max_prompt_lines_global}）", flush=True)

            # ✅ 关键修改：不再拼接 tensor，而是收集原始 tensor 列表
            image_tensors = []
            group_letter = chr(ord('A') + i - 1)
            for suffix in ['a', 'b', 'c']:
                img = kwargs.get(f"image_{group_letter}_{suffix}")
                if img is not None and img.shape[0] > 0:
                    # 支持 batch 输入（如 LoadImage 输出可能是 [N,H,W,C]）
                    for b in range(img.shape[0]):
                        image_tensors.append(img[b:b+1])  # 保持 [1,H,W,C] 格式

            if not image_tensors:
                continue

            # ✅ 根据实际 prompt_lines 决定 batch_count
            if len(prompt_lines) > 1:
                effective_batch_count = len(prompt_lines)
            else:
                user_batch = int(kwargs.get(f"batch_count_{i}", 1))
                effective_batch_count = max(1, min(10, user_batch))

            valid_tasks.append((i - 1, i, image_tensors, prompt_lines, effective_batch_count))

        if not valid_tasks:
            raise ValueError("至少需要一组有效的（提示词 + 至少1张参考图）")

        valid_tasks = valid_tasks[:global_concurrent_tasks]
        print(f"▶ 仅处理前 {len(valid_tasks)} 个有效组（受 global_concurrent_tasks={global_concurrent_tasks} 限制）", flush=True)

        with ThreadPoolExecutor(max_workers=len(valid_tasks)) as executor:
            futures = {}
            for out_idx, group_id, image_tensors, prompt_lines, batch_count in valid_tasks:
                future = executor.submit(
                    self.process_single_group_with_batch,
                    group_id, image_tensors, prompt_lines, batch_count,
                    runninghub_api_key, 全能Xinbao_api_key,
                    image_hosting, creds,
                    resolution, aspect_ratio, max_wait_time,
                    strategy
                )
                futures[future] = out_idx

            url_results = {}
            result_url_results = {}
            for future in as_completed(futures):
                out_idx = futures[future]
                try:
                    img_tensor, result_urls, ref_urls = future.result()
                    results[out_idx] = img_tensor
                    url_results[out_idx] = ref_urls
                    result_url_results[out_idx] = result_urls
                except Exception as e:
                    print(f"⚠️ 组 {out_idx + 1} 整体失败: {e}", flush=True)

        # 汇总所有真实成功图像
        all_real_images = []
        for img_tensor in results:
            if img_tensor.shape[1] > 64:  # 排除占位符
                all_real_images.append(img_tensor)

        if all_real_images:
            all_success_output = torch.cat(all_real_images, dim=0)
        else:
            all_success_output = torch.zeros((1, 1, 1, 3), dtype=torch.float32)

        # 汇总所有参考图URL
        url_lines = []
        for i in range(10):
            if i in url_results and url_results[i]:
                group_id = i + 1
                urls = url_results[i]
                url_lines.append(f"组{group_id}: " + ", ".join(urls))
            else:
                url_lines.append(f"组{i+1}: (无)")
        all_urls_str = "\n".join(url_lines)

        # 汇总所有结果图URL
        result_url_lines = []
        for i in range(10):
            if i in result_url_results and result_url_results[i]:
                group_id = i + 1
                urls = result_url_results[i]
                result_url_lines.append(f"组{group_id}: " + ", ".join(urls))
            else:
                result_url_lines.append(f"组{i+1}: (无)")
        all_result_urls_str = "\n".join(result_url_lines)

        return tuple(results) + (all_success_output, all_urls_str, all_result_urls_str)


NODE_CLASS_MAPPINGS = {
    "YK_HybridI2I_OSS": YKHybridI2IOSSNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "YK_HybridI2I_OSS": "YK-ComfyUI-HybridI2I-OSS"
}