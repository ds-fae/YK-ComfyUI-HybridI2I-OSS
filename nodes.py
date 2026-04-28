import os
import requests
import time
import random
import numpy as np
from PIL import Image
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
            optional_inputs[f"image_url_{group_letter}_a"] = ("STRING", {"forceInput": True, "placeholder": "参考图URL"})
            optional_inputs[f"image_url_{group_letter}_b"] = ("STRING", {"forceInput": True, "placeholder": "参考图URL"})
            optional_inputs[f"image_url_{group_letter}_c"] = ("STRING", {"forceInput": True, "placeholder": "参考图URL"})
            optional_inputs[f"presigned_url_{group_letter}"] = ("STRING", {"forceInput": True, "placeholder": "预签名URL（该组结果图上传地址）"})
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

                "runninghub_api_key": ("STRING", {"default": "", "placeholder": "RunningHub API 密钥"}),
                "全能Xinbao_api_key": ("STRING", {"default": "", "placeholder": "全能Xinbao API 密钥"}),

                "运行模式": (["预签名URL(正式)", "阿里云AK(测试+预览)"], {"default": "预签名URL(正式)"}),
                "oss_access_key_id": ("STRING", {"default": "", "placeholder": "阿里云 AccessKey ID"}),
                "oss_access_key_secret": ("STRING", {"default": "", "placeholder": "阿里云 AccessKey Secret"}),
                "oss_bucket_name": ("STRING", {"default": "", "placeholder": "OSS Bucket 名称"}),
                "oss_endpoint": ("STRING", {"default": "oss-cn-beijing.aliyuncs.com", "placeholder": "OSS Endpoint"}),
                "output_format": (["jpg", "png"], {"default": "jpg"}),
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
                "max_prompt_lines_global": ("INT", {
                    "default": -1,
                    "min": -1,
                    "max": 50,
                    "step": 1,
                    "tooltip": "【全局】每组最多使用多少行提示词（-1 = 不限制）"
                }),
            },
            "optional": optional_inputs
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("测试图像",)
    FUNCTION = "generate"
    CATEGORY = "YK-ComfyUI"

    def upload_to_aliyun_oss(self, pil_img, access_key_id, access_key_secret, bucket_name, endpoint, output_format):
        if not OSS_AVAILABLE:
            raise RuntimeError("未安装 oss2 库，请运行: pip install oss2")
        if not all([access_key_id.strip(), access_key_secret.strip(), bucket_name.strip()]):
            raise ValueError("请填写完整的阿里云 OSS 配置信息")

        date_str = time.strftime("%Y-%m-%d", time.localtime())
        timestamp = str(int(time.time() * 1000))
        random_suffix = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8))
        ext = 'jpg' if output_format.lower() in ('jpg', 'jpeg') else 'png'
        object_key = f"{date_str}/comfyui_rhart/{timestamp}_{random_suffix}.{ext}"

        auth = oss2.Auth(access_key_id.strip(), access_key_secret.strip())
        bucket = oss2.Bucket(auth, f'https://{endpoint.strip()}', bucket_name.strip())

        buf = BytesIO()
        if ext in ('jpg', 'jpeg'):
            if pil_img.mode in ('RGBA', 'P'):
                pil_img = pil_img.convert('RGB')
            pil_img.save(buf, format="JPEG", quality=95)
            content_type = 'image/jpeg'
        else:
            pil_img.save(buf, format="PNG")
            content_type = 'image/png'
        buf.seek(0)

        try:
            bucket.put_object(object_key, buf.getvalue(), headers={'Content-Type': content_type})
        except Exception as e:
            raise RuntimeError(f"阿里云 OSS 上传失败: {e}")

        return f"https://{bucket_name.strip()}.{endpoint.strip()}/{object_key}"

    def upload_via_presigned_url(self, pil_img, presigned_url, output_format):
        ext = output_format.lower()
        if ext not in ('jpg', 'jpeg', 'png'):
            ext = 'jpg'

        buf = BytesIO()
        if ext in ('jpg', 'jpeg'):
            if pil_img.mode in ('RGBA', 'P'):
                pil_img = pil_img.convert('RGB')
            pil_img.save(buf, format="JPEG", quality=95)
            content_type = 'image/jpeg'
        else:
            pil_img.save(buf, format="PNG")
            content_type = 'image/png'
        buf.seek(0)

        resp = requests.put(presigned_url, data=buf.getvalue(), headers={'Content-Type': content_type}, timeout=60)
        resp.raise_for_status()
        return presigned_url

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

    def process_single_group_with_batch(self, group_id, image_urls, prompt_list, batch_count,
                                       runninghub_api_key, banana_api_key,
                                       oss_access_key_id, oss_access_key_secret,
                                       oss_bucket_name, oss_endpoint,
                                       upload_mode, presigned_url, output_format,
                                       resolution, aspect_ratio, max_wait_time,
                                       strategy, show_preview_image):
        if not image_urls:
            raise RuntimeError(f"[组 {group_id}] 无有效参考图 URL")

        print(f"[组 {group_id}] 使用 {len(image_urls)} 个参考图 URL，开始生成 {batch_count} 个变体", flush=True)

        result_urls = []
        preview_pil = None
        with ThreadPoolExecutor(max_workers=batch_count) as executor:
            futures = {}
            for var_index in range(batch_count):
                future = executor.submit(
                    self._attempt_with_strategy,
                    group_id, var_index + 1, image_urls,
                    prompt_list[min(var_index, len(prompt_list) - 1)],
                    runninghub_api_key, banana_api_key,
                    resolution, aspect_ratio, max_wait_time,
                    strategy
                )
                futures[future] = var_index + 1

            for future in futures:
                var_id = futures[future]
                try:
                    pil_img = future.result()
                    if pil_img is not None:
                        if upload_mode == "预签名URL":
                            url = self.upload_via_presigned_url(pil_img, presigned_url, output_format)
                        else:
                            url = self.upload_to_aliyun_oss(
                                pil_img, oss_access_key_id, oss_access_key_secret,
                                oss_bucket_name, oss_endpoint, output_format
                            )
                        result_urls.append(url)
                        print(f"[组 {group_id} 变体 {var_id}] 结果图上传成功: {url}", flush=True)
                        if show_preview_image == "是" and preview_pil is None:
                            preview_pil = pil_img
                except Exception as e:
                    print(f"⚠️ [组 {group_id} 变体 {var_id}] 执行或上传异常（已跳过）: {e}", flush=True)

        return result_urls, preview_pil

    def generate(self,
                 社区版_最大尝试次数,
                 全能Xinbao_最大尝试次数,
                 官方PRO版_最大尝试次数,
                 runninghub_api_key, 全能Xinbao_api_key,
                 运行模式,
                 oss_access_key_id, oss_access_key_secret, oss_bucket_name, oss_endpoint,
                 output_format,
                 resolution, aspect_ratio, seed, global_concurrent_tasks, max_wait_time,
                 max_prompt_lines_global,
                 **kwargs):

        # 从运行模式推导上传方式和预览开关
        if 运行模式 == "预签名URL(正式)":
            upload_mode = "预签名URL"
            show_preview_image = "否"
        else:
            upload_mode = "阿里云AK"
            show_preview_image = "是"

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

        if upload_mode == "阿里云AK":
            if not OSS_AVAILABLE:
                raise ValueError("阿里云AK模式需要 oss2，请运行: pip install oss2")
            if not all([oss_access_key_id.strip(), oss_access_key_secret.strip(), oss_bucket_name.strip()]):
                raise ValueError("阿里云AK模式需要完整的OSS配置")

        global_concurrent_tasks = min(max(1, int(global_concurrent_tasks)), 10)
        max_wait_time = min(max(30, int(max_wait_time)), 600)

        max_prompt_lines_global = int(max_prompt_lines_global)
        if max_prompt_lines_global == 0:
            max_prompt_lines_global = -1

        valid_tasks = []
        for i in range(1, 11):
            raw_prompt = kwargs.get(f"prompt_{i}", "")
            prompt_lines = [line.strip() for line in raw_prompt.split('\n') if line.strip()]
            if not prompt_lines:
                continue

            if max_prompt_lines_global > 0 and len(prompt_lines) > max_prompt_lines_global:
                prompt_lines = prompt_lines[:max_prompt_lines_global]
                print(f"[组 {i}] 提示词行数被全局限制为 {len(prompt_lines)} 行", flush=True)

            image_urls = []
            group_letter = chr(ord('A') + i - 1)
            for suffix in ['a', 'b', 'c']:
                url = kwargs.get(f"image_url_{group_letter}_{suffix}", "")
                if isinstance(url, str) and url.strip():
                    image_urls.append(url.strip())

            if not image_urls:
                continue

            presigned_url = ""
            if upload_mode == "预签名URL":
                presigned_url = kwargs.get(f"presigned_url_{group_letter}", "")
                if isinstance(presigned_url, str):
                    presigned_url = presigned_url.strip()
                if not presigned_url:
                    print(f"⚠️ [组 {i}] 预签名URL模式但缺少 presigned_url_{group_letter}，已跳过", flush=True)
                    continue

            if len(prompt_lines) > 1:
                effective_batch_count = len(prompt_lines)
            else:
                user_batch = int(kwargs.get(f"batch_count_{i}", 1))
                effective_batch_count = max(1, min(10, user_batch))

            valid_tasks.append((i, image_urls, prompt_lines, effective_batch_count, presigned_url))

        if not valid_tasks:
            raise ValueError("至少需要一组有效的（提示词 + 至少1个参考图URL）")

        valid_tasks = valid_tasks[:global_concurrent_tasks]
        print(f"▶ 仅处理前 {len(valid_tasks)} 个有效组（受 global_concurrent_tasks={global_concurrent_tasks} 限制）", flush=True)

        result_url_lines = []
        all_preview_pils = []
        with ThreadPoolExecutor(max_workers=len(valid_tasks)) as executor:
            futures = {}
            for group_id, image_urls, prompt_lines, batch_count, presigned_url in valid_tasks:
                future = executor.submit(
                    self.process_single_group_with_batch,
                    group_id, image_urls, prompt_lines, batch_count,
                    runninghub_api_key, 全能Xinbao_api_key,
                    oss_access_key_id, oss_access_key_secret, oss_bucket_name, oss_endpoint,
                    upload_mode, presigned_url, output_format,
                    resolution, aspect_ratio, max_wait_time,
                    strategy, show_preview_image
                )
                futures[future] = group_id

            for future in as_completed(futures):
                group_id = futures[future]
                try:
                    result_urls, preview_pil = future.result()
                    if result_urls:
                        result_url_lines.append(f"组{group_id}: " + ", ".join(result_urls))
                    else:
                        result_url_lines.append(f"组{group_id}: (无)")
                    if preview_pil is not None:
                        all_preview_pils.append(preview_pil)
                except Exception as e:
                    print(f"⚠️ 组 {group_id} 整体失败: {e}", flush=True)
                    result_url_lines.append(f"组{group_id}: (失败)")

        result_url_lines.sort(key=lambda x: int(x.split(':')[0].replace('组', '')))
        if result_url_lines:
            print("\n".join(result_url_lines), flush=True)

        # 构建测试图像输出
        if show_preview_image == "是" and all_preview_pils:
            preview_pil = all_preview_pils[0].convert("RGB")
            img_array = np.array(preview_pil).astype(np.float32) / 255.0
            preview_tensor = img_array.reshape(1, img_array.shape[0], img_array.shape[1], img_array.shape[2])
        else:
            preview_tensor = np.zeros((1, 64, 64, 3), dtype=np.float32)

        return (preview_tensor,)


NODE_CLASS_MAPPINGS = {
    "YK_HybridI2I_OSS": YKHybridI2IOSSNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "YK_HybridI2I_OSS": "YK-ComfyUI-HybridI2I-OSS"
}
