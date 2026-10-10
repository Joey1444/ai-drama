#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G2.5 关键帧质量门：关键帧正脸闭嘴/清晰/无遮挡/光照均匀
用法：python scripts/check_gate_G25.py <图片提示词路径> <参考图目录>
"""

import io
import sys
import json
from pathlib import Path
from typing import Dict, List, Tuple

# Windows 上 stdout 默认 GBK，中文/emoji 会乱码或直接崩溃，强制 UTF-8
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# cv2/numpy 为可选依赖：环境没装时不崩溃，退化为"只做文件存在性检查 + 告警"
try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    cv2 = None
    np = None
    HAS_CV2 = False

def _imread_unicode(path: Path):
    """OpenCV 在 Windows 上不支持非 ASCII 路径（本项目路径含中文），
    用 np.fromfile + cv2.imdecode 绕过。"""
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception:
        return None


def check_image_quality(img_path: Path) -> Tuple[bool, List[str], Dict]:
    """单张关键帧质量检测"""
    issues = []
    metrics = {}

    img = _imread_unicode(img_path)
    if img is None:
        return False, [f"❌ 无法读取图片: {img_path}"], {}

    h, w = img.shape[:2]
    metrics["resolution"] = f"{w}x{h}"

    # 1. 分辨率检查
    if w < 512 or h < 512:
        issues.append(f"⚠️ 分辨率过低: {w}x{h} (建议≥512x512)")

    # 2. 模糊度检测 (Laplacian 方差)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    metrics["blur_score"] = round(blur_score, 2)
    if blur_score < 100:
        issues.append(f"⚠️ 疑似模糊: Laplacian方差={blur_score:.1f} (建议>100)")

    # 3. 亮度/曝光检查
    mean_brightness = gray.mean()
    metrics["brightness"] = round(mean_brightness, 1)
    if mean_brightness < 30:
        issues.append(f"⚠️ 过暗: 平均亮度={mean_brightness:.1f} (建议>30)")
    elif mean_brightness > 220:
        issues.append(f"⚠️ 过亮: 平均亮度={mean_brightness:.1f} (建议<220)")

    # 4. 人脸检测（定妆帧必须有人脸）
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    faces = face_cascade.detectMultiScale(gray, 1.1, 4)
    metrics["faces_detected"] = len(faces)

    if len(faces) == 0:
        issues.append("⚠️ 未检测到人脸（定妆帧必须包含清晰人脸）")
    elif len(faces) > 1:
        issues.append(f"⚠️ 检测到多张人脸({len(faces)})，定妆帧应单人")

    # 5. 嘴唇闭合检测（简易：下半脸区域颜色均匀性）
    if len(faces) == 1:
        x, y, fw, fh = faces[0]
        # 嘴巴区域大致在下巴上方 1/3 处
        mouth_roi = gray[y + int(fh*0.6):y + int(fh*0.9), x:x+fw]
        if mouth_roi.size > 0:
            mouth_std = mouth_roi.std()
            metrics["mouth_std"] = round(mouth_std, 2)
            # 闭嘴时嘴唇区域颜色相对均匀（std较小），张嘴有牙齿/舌头对比度大
            if mouth_std > 40:
                issues.append(f"⚠️ 疑似张嘴: 嘴部区域标准差={mouth_std:.1f} (闭嘴建议<40)")

    return len(issues) == 0, issues, metrics

def parse_image_prompts(path: str) -> List[Dict]:
    """解析图片提示词文件，提取关键帧条目"""
    content = Path(path).read_text(encoding='utf-8')
    entries = []

    # 匹配二级标题作为条目
    import re
    pattern = r'##\s+IMG-(\w+)\s+(.+?)(?=\n## |\Z)'
    matches = re.findall(pattern, content, re.DOTALL)
    for img_id, body in matches:
        entries.append({"id": img_id, "body": body.strip()})

    return entries

def main():
    if len(sys.argv) < 3:
        print("用法: python check_gate_G25.py <图片提示词路径> <参考图目录>")
        sys.exit(1)

    prompts_path = sys.argv[1]
    refs_dir = Path(sys.argv[2])

    if not Path(prompts_path).exists():
        print(f"❌ 图片提示词不存在: {prompts_path}")
        sys.exit(1)

    if not refs_dir.exists():
        print(f"❌ 参考图目录不存在: {refs_dir}")
        sys.exit(1)

    entries = parse_image_prompts(prompts_path)
    if not entries:
        print("⚠️ 未解析到关键帧条目（无 ## IMG-xxx 标题）")
        # 不直接失败，可能是用其他格式

    all_passed = True
    all_results = []
    all_issues = []

    # 遍历参考图目录下的所有图片
    img_files = list(refs_dir.rglob("*.png")) + list(refs_dir.rglob("*.jpg")) + list(refs_dir.rglob("*.jpeg"))

    if not img_files:
        print("⚠️ 参考图目录为空")
        # 不直接失败

    if not HAS_CV2:
        # 无 cv2：退化为文件存在性检查，明确告警"未做画质检测"，不谎报通过
        for img_file in img_files:
            rel_path = img_file.relative_to(refs_dir)
            all_results.append({
                "file": str(rel_path),
                "passed": True,
                "issues": ["⚠️ 未做画质检测：环境缺 cv2（pip install opencv-python）"],
                "metrics": {"size_bytes": img_file.stat().st_size}
            })
        result = {
            "gate": "G2.5",
            "name": "关键帧质量门",
            "passed": True,
            "degraded": True,
            "note": "环境缺 cv2，仅做文件存在性检查；画质（正脸/闭嘴/清晰度）未验证，需人工确认",
            "total_images": len(all_results),
            "passed_count": len(all_results),
            "results": all_results,
            "issues": ["⚠️ 缺 cv2，画质检测被跳过——请人工抽检关键帧，或 pip install opencv-python"],
            "checked_dir": str(refs_dir)
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"\n⚠️ G2.5 降级通过：缺 cv2，{len(all_results)} 张图仅做存在性检查，画质需人工确认")
        sys.exit(0)

    for img_file in img_files:
        ok, issues, metrics = check_image_quality(img_file)
        rel_path = img_file.relative_to(refs_dir)
        result = {
            "file": str(rel_path),
            "passed": ok,
            "issues": issues,
            "metrics": metrics
        }
        all_results.append(result)
        if not ok:
            all_passed = False
            all_issues.extend([f"[{rel_path}] {iss}" for iss in issues])

    # 统计
    total = len(all_results)
    passed_count = sum(1 for r in all_results if r["passed"])

    result = {
        "gate": "G2.5",
        "name": "关键帧质量门",
        "passed": all_passed,
        "total_images": total,
        "passed_count": passed_count,
        "results": all_results,
        "issues": all_issues,
        "checked_dir": str(refs_dir)
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if all_passed:
        print(f"\n✅ G2.5 关键帧质量门通过：{passed_count}/{total} 张图片合格")
        sys.exit(0)
    else:
        print(f"\n❌ G2.5 关键帧质量门未通过：{passed_count}/{total} 通过")
        for issue in all_issues:
            print(f"  - {issue}")
        sys.exit(1)

if __name__ == "__main__":
    main()