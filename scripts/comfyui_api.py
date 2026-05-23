#!/usr/bin/env Python3
"""
ComfyUI API 交互模块 (ComfyUI API Client)

功能概述：
1. 检查ComfyUI服务状态
2. 提交工作流（prompt）到ComfyUI
3. 轮询任务状态直到完成或超时
4. 获取任务输出的图片/视频路径
5. 批量等待多个任务完成

依赖：
  - urllib (Python标准库)
  - json (Python标准库)

ComfyUI API文档参考：
  - POST /prompt          提交工作流
  - GET  /history/{id}    查询任务历史
  - GET  /system_stats    系统状态检查
  - WS   /ws              WebSocket实时状态（可选）

使用方式：
  from comfyui_api import check_comfyui_running, submit_workflow, poll_prompt_status

  if check_comfyui_running():
      prompt_id = submit_workflow(workflow_dict)
      result = poll_prompt_status(prompt_id, timeout=600)
      images = get_output_images(prompt_id)
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional

# 项目内部模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config


# 默认ComfyUI API地址
DEFAULT_BASE_URL = config.COMFYUI_API_URL

# 轮询配置
DEFAULT_POLL_INTERVAL = 3      # 轮询间隔（秒）
DEFAULT_TIMEOUT = 600           # 默认超时（秒）= 10分钟
WS_TIMEOUT = 30                 # WebSocket连接超时


# ============ 基础HTTP请求 ============

def _http_get(url: str, timeout: int = 10) -> dict:
    """
    发送GET请求

    参数：
        url: 请求URL
        timeout: 超时时间（秒）

    返回：
        解析后的JSON字典
    """
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_post(url: str, data: dict, timeout: int = 30) -> dict:
    """
    发送POST请求

    参数：
        url: 请求URL
        data: 请求体（字典，自动转JSON）
        timeout: 超时时间（秒）

    返回：
        解析后的JSON字典
    """
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ============ 服务状态检查 ============

def check_comfyui_running(base_url: str = DEFAULT_BASE_URL) -> bool:
    """
    检查ComfyUI服务是否运行

    通过访问 /system_stats 端点判断服务是否在线。

    参数：
        base_url: ComfyUI API基础URL

    返回：
        True=服务运行中, False=服务不可用
    """
    try:
        result = _http_get(f"{base_url}/system_stats", timeout=5)
        system_info = result.get("system", {})
        devices = result.get("devices", [])
        if devices:
            vram_info = devices[0].get("vram_total", "unknown")
            print(f"  [ComfyUI] 服务在线 | VRAM: {vram_info}")
        else:
            print(f"  [ComfyUI] 服务在线 | 设备信息未获取")
        return True
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError, OSError) as e:
        print(f"  [ComfyUI] 服务离线: {e}")
        return False


# ============ 工作流提交 ============

def submit_workflow(workflow: dict, base_url: str = DEFAULT_BASE_URL) -> str:
    """
    提交工作流到ComfyUI，返回prompt_id

    参数：
        workflow: ComfyUI工作流字典（API格式）
        base_url: ComfyUI API基础URL

    返回：
        prompt_id 字符串

    异常：
        RuntimeError: 提交失败时抛出
    """
    try:
        result = _http_post(f"{base_url}/prompt", {"prompt": workflow}, timeout=30)
        prompt_id = result.get("prompt_id")
        number = result.get("number", "?")

        if not prompt_id:
            error_info = result.get("error", result.get("node_errors", "unknown error"))
            raise RuntimeError(f"ComfyUI提交失败: {error_info}")

        print(f"  [ComfyUI] 已提交工作流 | prompt_id: {prompt_id} | number: {number}")
        return prompt_id

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ComfyUI HTTP错误 {e.code}: {error_body[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"ComfyUI连接失败: {e.reason}")


def submit_workflow_with_images(workflow: dict, images: dict, base_url: str = DEFAULT_BASE_URL) -> str:
    """
    提交工作流并上传图片（用于I2V等需要输入图片的工作流）

    参数：
        workflow: ComfyUI工作流字典
        images: 图片映射 {node_id: {filename, subfolder, type}} 或 {node_id: image_path}
        base_url: ComfyUI API基础URL

    返回：
        prompt_id 字符串
    """
    # 如果提供了图片路径，需要先上传
    for node_id, img_data in images.items():
        if isinstance(img_data, str):
            # img_data是本地路径，需要上传到ComfyUI
            upload_result = upload_image(img_data, base_url)
            # 在工作流中设置图片节点
            node_id_str = str(node_id)
            if node_id_str in workflow:
                workflow[node_id_str]["inputs"]["image"] = upload_result.get("name", os.path.basename(img_data))

    return submit_workflow(workflow, base_url)


def upload_image(image_path: str, base_url: str = DEFAULT_BASE_URL, overwrite: bool = True) -> dict:
    """
    上传图片到ComfyUI的input目录

    参数：
        image_path: 本地图片文件路径
        base_url: ComfyUI API基础URL
        overwrite: 是否覆盖同名文件

    返回：
        上传结果 {"name": "filename.png", "subfolder": "", "type": "input"}
    """
    import mimetypes

    filename = os.path.basename(image_path)

    # 构建multipart表单数据
    boundary = "----ComfyUIUploadBoundary7MA4YWxkTrZu0gW"

    with open(image_path, "rb") as f:
        image_data = f.read()

    mime_type = mimetypes.guess_type(image_path)[0] or "image/png"

    body = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\n"
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8") + image_data + f"\r\n--{boundary}\r\n".encode("utf-8")

    # overwrite 参数
    body += (
        f"Content-Disposition: form-data; name=\"overwrite\"\r\n\r\n"
        f"{'true' if overwrite else 'false'}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        print(f"  [ComfyUI] 图片已上传: {result.get('name', filename)}")
        return result


# ============ 任务状态轮询 ============

def poll_prompt_status(
    prompt_id: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = DEFAULT_TIMEOUT,
    poll_interval: int = DEFAULT_POLL_INTERVAL,
) -> dict:
    """
    轮询任务状态直到完成或超时

    状态判断逻辑：
    - 通过 /history/{prompt_id} 查询任务历史
    - 如果历史中存在该prompt_id且有outputs，则任务完成
    - 如果历史中存在且status.status_str为错误，则任务失败
    - 如果历史中不存在，任务仍在队列或执行中

    参数：
        prompt_id: 任务ID
        base_url: ComfyUI API基础URL
        timeout: 超时时间（秒）
        poll_interval: 轮询间隔（秒）

    返回：
        任务结果字典 {
            "prompt_id": str,
            "status": "completed" | "failed" | "timeout",
            "outputs": dict,       # ComfyUI输出的节点结果
            "duration_s": float,   # 实际等待时长
            "error": str | None,   # 错误信息
        }
    """
    start_time = time.time()
    last_status = "pending"

    print(f"  [ComfyUI] 开始轮询任务 {prompt_id[:12]}... (超时: {timeout}s)")

    while True:
        elapsed = time.time() - start_time

        if elapsed > timeout:
            print(f"  [ComfyUI] 任务超时: {prompt_id[:12]} ({elapsed:.0f}s > {timeout}s)")
            return {
                "prompt_id": prompt_id,
                "status": "timeout",
                "outputs": {},
                "duration_s": elapsed,
                "error": f"任务超时 ({timeout}s)",
            }

        try:
            history = _http_get(f"{base_url}/history/{prompt_id}", timeout=10)

            if prompt_id in history:
                task_info = history[prompt_id]
                status_info = task_info.get("status", {})
                status_str = status_info.get("status_str", "unknown")
                completed = status_info.get("completed", False)
                outputs = task_info.get("outputs", {})

                # 检查是否有错误
                if status_str == "error" or status_info.get("messages", []):
                    error_msgs = status_info.get("messages", [])
                    error_text = ""
                    for msg in error_msgs:
                        if isinstance(msg, (list, tuple)) and len(msg) >= 2:
                            error_text += f"[{msg[0]}] {msg[1]}\n"
                        else:
                            error_text += str(msg) + "\n"

                    if status_str == "error":
                        print(f"  [ComfyUI] 任务失败: {prompt_id[:12]} | 错误: {error_text[:200]}")
                        return {
                            "prompt_id": prompt_id,
                            "status": "failed",
                            "outputs": outputs,
                            "duration_s": elapsed,
                            "error": error_text[:500],
                        }

                # 任务完成
                if completed or outputs:
                    print(f"  [ComfyUI] 任务完成: {prompt_id[:12]} | 耗时: {elapsed:.1f}s | 输出节点: {list(outputs.keys())}")
                    return {
                        "prompt_id": prompt_id,
                        "status": "completed",
                        "outputs": outputs,
                        "duration_s": elapsed,
                        "error": None,
                    }

                # 状态更新
                if status_str != last_status:
                    print(f"  [ComfyUI] 任务状态: {status_str} ({elapsed:.0f}s)")
                    last_status = status_str

            # 任务还在队列中
            else:
                # 尝试检查队列
                try:
                    queue_info = _http_get(f"{base_url}/queue", timeout=5)
                    queue_running = queue_info.get("queue_running", [])
                    queue_pending = queue_info.get("queue_pending", [])

                    in_running = any(
                        item[1] == prompt_id for item in queue_running
                        if isinstance(item, (list, tuple)) and len(item) > 1
                    )
                    in_pending = any(
                        item[1] == prompt_id for item in queue_pending
                        if isinstance(item, (list, tuple)) and len(item) > 1
                    )

                    if in_running:
                        current_status = "executing"
                    elif in_pending:
                        current_status = "queued"
                    else:
                        current_status = "waiting"

                    if current_status != last_status:
                        print(f"  [ComfyUI] 任务状态: {current_status} ({elapsed:.0f}s)")
                        last_status = current_status
                except Exception:
                    pass

        except (urllib.error.URLError, ConnectionRefusedError, TimeoutError, OSError) as e:
            print(f"  [ComfyUI] 轮询连接异常: {e}，继续重试...")

        # 等待下一次轮询
        time.sleep(poll_interval)


# ============ 输出获取 ============

def get_output_images(
    prompt_id: str,
    base_url: str = DEFAULT_BASE_URL,
    output_dir: Optional[str] = None,
) -> list[str]:
    """
    获取任务输出的图片路径列表

    参数：
        prompt_id: 任务ID
        base_url: ComfyUI API基础URL
        output_dir: 下载图片到本地目录（None则返回URL列表）

    返回：
        图片路径列表（本地路径或URL）
    """
    try:
        history = _http_get(f"{base_url}/history/{prompt_id}", timeout=10)
    except Exception as e:
        print(f"  [ComfyUI] 获取输出失败: {e}")
        return []

    if prompt_id not in history:
        print(f"  [ComfyUI] 任务历史未找到: {prompt_id[:12]}")
        return []

    outputs = history[prompt_id].get("outputs", {})
    image_list = []

    for node_id, node_output in outputs.items():
        images = node_output.get("images", [])
        for img in images:
            filename = img.get("filename", "")
            subfolder = img.get("subfolder", "")
            img_type = img.get("type", "output")

            if output_dir:
                # 下载图片到本地
                local_path = _download_output(filename, subfolder, img_type, base_url, output_dir)
                if local_path:
                    image_list.append(local_path)
            else:
                # 返回ComfyUI的URL
                params = urllib.parse.urlencode({
                    "filename": filename,
                    "subfolder": subfolder,
                    "type": img_type,
                })
                url = f"{base_url}/view?{params}"
                image_list.append(url)

    if image_list:
        print(f"  [ComfyUI] 获取到 {len(image_list)} 张图片")
    return image_list


def get_output_videos(
    prompt_id: str,
    base_url: str = DEFAULT_BASE_URL,
    output_dir: Optional[str] = None,
) -> list[str]:
    """
    获取任务输出的视频路径列表

    参数：
        prompt_id: 任务ID
        base_url: ComfyUI API基础URL
        output_dir: 下载视频到本地目录（None则返回URL列表）

    返回：
        视频路径列表（本地路径或URL）
    """
    try:
        history = _http_get(f"{base_url}/history/{prompt_id}", timeout=10)
    except Exception as e:
        print(f"  [ComfyUI] 获取输出失败: {e}")
        return []

    if prompt_id not in history:
        print(f"  [ComfyUI] 任务历史未找到: {prompt_id[:12]}")
        return []

    outputs = history[prompt_id].get("outputs", {})
    video_list = []

    for node_id, node_output in outputs.items():
        # 视频可能在 "videos" 或 "gifs" 字段中
        videos = node_output.get("videos", []) + node_output.get("gifs", [])
        for vid in videos:
            filename = vid.get("filename", "")
            subfolder = vid.get("subfolder", "")
            vid_type = vid.get("type", "output")

            if output_dir:
                local_path = _download_output(filename, subfolder, vid_type, base_url, output_dir)
                if local_path:
                    video_list.append(local_path)
            else:
                params = urllib.parse.urlencode({
                    "filename": filename,
                    "subfolder": subfolder,
                    "type": vid_type,
                })
                url = f"{base_url}/view?{params}"
                video_list.append(url)

    if video_list:
        print(f"  [ComfyUI] 获取到 {len(video_list)} 个视频")
    return video_list


def _download_output(
    filename: str,
    subfolder: str,
    file_type: str,
    base_url: str,
    output_dir: str,
) -> Optional[str]:
    """
    从ComfyUI下载输出文件到本地

    参数：
        filename: 文件名
        subfolder: 子目录
        file_type: 类型 (output/input/temp)
        base_url: ComfyUI API基础URL
        output_dir: 本地下载目录

    返回：
        本地文件路径，失败返回None
    """
    os.makedirs(output_dir, exist_ok=True)

    params = urllib.parse.urlencode({
        "filename": filename,
        "subfolder": subfolder,
        "type": file_type,
    })
    url = f"{base_url}/view?{params}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()

        local_path = os.path.join(output_dir, filename)
        with open(local_path, "wb") as f:
            f.write(data)

        print(f"  [ComfyUI] 已下载: {filename} ({len(data)/1024:.1f}KB)")
        return os.path.abspath(local_path)

    except Exception as e:
        print(f"  [ComfyUI] 下载失败: {filename} - {e}")
        return None


# ============ 批量任务管理 ============

def wait_for_all_tasks(
    prompt_ids: list[str],
    base_url: str = DEFAULT_BASE_URL,
    poll_interval: int = DEFAULT_POLL_INTERVAL,
    timeout_per_task: int = DEFAULT_TIMEOUT,
    max_concurrent_timeout: int = 3600,
) -> dict:
    """
    等待所有任务完成，返回 {prompt_id: status} 映射

    参数：
        prompt_ids: 任务ID列表
        base_url: ComfyUI API基础URL
        poll_interval: 轮询间隔（秒）
        timeout_per_task: 单个任务超时（秒）
        max_concurrent_timeout: 总超时（秒），用于所有任务的总等待时间

    返回：
        任务状态映射 {
            "prompt_id_1": {"status": "completed", "outputs": {...}, "duration_s": ...},
            "prompt_id_2": {"status": "failed", "outputs": {}, "duration_s": ..., "error": "..."},
            ...
        }
    """
    results = {}
    pending_ids = set(prompt_ids)
    start_time = time.time()

    print(f"  [ComfyUI] 等待 {len(prompt_ids)} 个任务完成...")

    while pending_ids:
        elapsed = time.time() - start_time

        if elapsed > max_concurrent_timeout:
            print(f"  [ComfyUI] 总等待超时 ({max_concurrent_timeout}s)")
            for pid in pending_ids:
                results[pid] = {
                    "prompt_id": pid,
                    "status": "timeout",
                    "outputs": {},
                    "duration_s": elapsed,
                    "error": "总超时",
                }
            break

        # 检查每个pending任务
        completed_this_round = []
        for pid in list(pending_ids):
            try:
                history = _http_get(f"{base_url}/history/{pid}", timeout=10)

                if pid in history:
                    task_info = history[pid]
                    status_info = task_info.get("status", {})
                    outputs = task_info.get("outputs", {})
                    status_str = status_info.get("status_str", "unknown")
                    completed = status_info.get("completed", False)

                    if status_str == "error":
                        error_msgs = status_info.get("messages", [])
                        error_text = "; ".join(str(m) for m in error_msgs) if error_msgs else "unknown error"
                        results[pid] = {
                            "prompt_id": pid,
                            "status": "failed",
                            "outputs": outputs,
                            "duration_s": time.time() - start_time,
                            "error": error_text[:500],
                        }
                        completed_this_round.append(pid)

                    elif completed or outputs:
                        results[pid] = {
                            "prompt_id": pid,
                            "status": "completed",
                            "outputs": outputs,
                            "duration_s": time.time() - start_time,
                            "error": None,
                        }
                        completed_this_round.append(pid)

            except Exception:
                pass  # 继续轮询

        for pid in completed_this_round:
            pending_ids.discard(pid)

        if completed_this_round:
            print(f"  [ComfyUI] 完成 {len(completed_this_round)} 个 | 剩余 {len(pending_ids)} 个 | 已等待 {elapsed:.0f}s")

        # 检查单个任务是否超过超时时间
        timed_out = []
        for pid in list(pending_ids):
            task_elapsed = time.time() - start_time
            if task_elapsed > timeout_per_task:
                results[pid] = {
                    "prompt_id": pid,
                    "status": "timeout",
                    "outputs": {},
                    "duration_s": task_elapsed,
                    "error": f"单任务超时 ({timeout_per_task}s)",
                }
                timed_out.append(pid)
        for pid in timed_out:
            pending_ids.discard(pid)

        if pending_ids:
            time.sleep(poll_interval)

    # 汇总结果
    completed_count = sum(1 for r in results.values() if r["status"] == "completed")
    failed_count = sum(1 for r in results.values() if r["status"] == "failed")
    timeout_count = sum(1 for r in results.values() if r["status"] == "timeout")

    print(f"  [ComfyUI] 全部任务完成: {completed_count}成功 / {failed_count}失败 / {timeout_count}超时")

    return results


# ============ 工作流批量提交 ============

def submit_workflows_from_dir(
    workflow_dir: str,
    pattern: str = "*_sdxl.json",
    base_url: str = DEFAULT_BASE_URL,
) -> list[str]:
    """
    从目录批量提交工作流文件

    参数：
        workflow_dir: 工作流文件目录
        pattern: 文件匹配模式（glob风格）
        base_url: ComfyUI API基础URL

    返回：
        prompt_id列表
    """
    import glob

    workflow_files = sorted(glob.glob(os.path.join(workflow_dir, pattern)))

    if not workflow_files:
        print(f"  [ComfyUI] 未找到匹配 {pattern} 的工作流文件")
        return []

    prompt_ids = []
    for wf_path in workflow_files:
        try:
            with open(wf_path, "r", encoding="utf-8") as f:
                workflow = json.load(f)

            prompt_id = submit_workflow(workflow, base_url)
            prompt_ids.append(prompt_id)
            print(f"  [ComfyUI] 已提交: {os.path.basename(wf_path)} -> {prompt_id[:12]}")

        except Exception as e:
            print(f"  [ComfyUI] 提交失败: {os.path.basename(wf_path)} - {e}")

    print(f"  [ComfyUI] 共提交 {len(prompt_ids)}/{len(workflow_files)} 个工作流")
    return prompt_ids


# ============ 队列管理 ============

def get_queue_status(base_url: str = DEFAULT_BASE_URL) -> dict:
    """
    获取ComfyUI任务队列状态

    参数：
        base_url: ComfyUI API基础URL

    返回：
        队列状态 {"running": int, "pending": int, "running_details": [...], "pending_details": [...]}
    """
    try:
        queue_info = _http_get(f"{base_url}/queue", timeout=5)
        running = queue_info.get("queue_running", [])
        pending = queue_info.get("queue_pending", [])

        return {
            "running": len(running),
            "pending": len(pending),
            "running_details": running,
            "pending_details": pending,
        }
    except Exception as e:
        print(f"  [ComfyUI] 获取队列状态失败: {e}")
        return {"running": 0, "pending": 0, "running_details": [], "pending_details": []}


def interrupt_current(base_url: str = DEFAULT_BASE_URL) -> bool:
    """
    中断当前正在执行的任务

    参数：
        base_url: ComfyUI API基础URL

    返回：
        是否成功中断
    """
    try:
        req = urllib.request.Request(
            f"{base_url}/interrupt",
            data=b"",
            method="POST",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            print("  [ComfyUI] 已发送中断请求")
            return True
    except Exception as e:
        print(f"  [ComfyUI] 中断失败: {e}")
        return False


def clear_queue(base_url: str = DEFAULT_BASE_URL) -> bool:
    """
    清空任务队列

    参数：
        base_url: ComfyUI API基础URL

    返回：
        是否成功清空
    """
    try:
        req = urllib.request.Request(
            f"{base_url}/queue",
            data=json.dumps({"delete": "All"}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            print("  [ComfyUI] 队列已清空")
            return True
    except Exception as e:
        print(f"  [ComfyUI] 清空队列失败: {e}")
        return False


# ============ 独立运行入口 ============

def main():
    """独立运行时的入口"""
    import argparse

    parser = argparse.ArgumentParser(description="ComfyUI API 交互工具")
    parser.add_argument("--url", default=DEFAULT_BASE_URL, help="ComfyUI API地址")
    parser.add_argument("--check", action="store_true", help="检查ComfyUI服务状态")
    parser.add_argument("--submit", help="提交工作流JSON文件")
    parser.add_argument("--poll", help="轮询指定prompt_id的状态")
    parser.add_argument("--images", help="获取指定prompt_id的输出图片")
    parser.add_argument("--videos", help="获取指定prompt_id的输出视频")
    parser.add_argument("--download-dir", default="./comfyui_output", help="下载输出文件的目录")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="超时时间（秒）")

    args = parser.parse_args()

    if args.check:
        running = check_comfyui_running(args.url)
        if running:
            queue = get_queue_status(args.url)
            print(f"  队列: {queue['running']} 运行中, {queue['pending']} 等待中")
        else:
            print("  ComfyUI服务未运行")
        return

    if args.submit:
        with open(args.submit, "r", encoding="utf-8") as f:
            workflow = json.load(f)
        prompt_id = submit_workflow(workflow, args.url)
        print(f"  prompt_id: {prompt_id}")

        # 自动轮询
        result = poll_prompt_status(prompt_id, args.url, timeout=args.timeout)
        print(f"  状态: {result['status']}")
        if result['status'] == 'completed':
            images = get_output_images(prompt_id, args.url, args.download_dir)
            videos = get_output_videos(prompt_id, args.url, args.download_dir)
            print(f"  输出: {len(images)} 图片, {len(videos)} 视频")
        return

    if args.poll:
        result = poll_prompt_status(args.poll, args.url, timeout=args.timeout)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if args.images:
        paths = get_output_images(args.images, args.url, args.download_dir)
        for p in paths:
            print(f"  {p}")
        return

    if args.videos:
        paths = get_output_videos(args.videos, args.url, args.download_dir)
        for p in paths:
            print(f"  {p}")
        return

    # 默认：显示帮助
    print("使用 --check 检查服务状态, --submit 提交工作流, --poll 轮询状态")


if __name__ == "__main__":
    main()
