"""
文件上传路由
"""
import os
import uuid
from datetime import datetime
from fastapi import APIRouter, File, UploadFile, HTTPException
import shutil

router = APIRouter()

# 上传目录
UPLOAD_DIR = "/app/static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 允许的图片 MIME 类型和对应的魔数（文件头）
ALLOWED_TYPES = {
    "image/jpeg": {"ext": "jpg", "magic": [b"\xff\xd8\xff"]},
    "image/png":  {"ext": "png", "magic": [b"\x89PNG"]},
    "image/gif":  {"ext": "gif", "magic": [b"GIF87a", b"GIF89a"]},
    "image/webp": {"ext": "webp", "magic": [b"RIFF", b"WEBP"]},
}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def _validate_and_save(file: UploadFile) -> str:
    """
    验证图片安全并保存。
    - 校验 MIME type（客户端可伪造，所以也检查魔数）
    - 忽略用户输入的扩展名，始终使用安全扩展名
    - 检查文件大小
    - 返回保存后的文件名
    """
    if not file.content_type or file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="只支持 JPG/PNG/GIF/WebP 格式")

    contents = file.file.read() if hasattr(file, 'file') else file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="图片大小不能超过 5MB")

    if len(contents) < 12:
        raise HTTPException(status_code=400, detail="文件内容无效")

    # 魔数校验（防伪造）
    info = ALLOWED_TYPES[file.content_type]
    magic_ok = any(contents.startswith(m) for m in info["magic"])
    if not magic_ok:
        raise HTTPException(status_code=400, detail="文件内容无效，不是有效的图片")

    # 强制使用安全的扩展名，完全忽略用户输入
    safe_ext = info["ext"]
    safe_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:12]}.{safe_ext}"
    filepath = os.path.join(UPLOAD_DIR, safe_filename)

    with open(filepath, "wb") as f:
        f.write(contents)

    return safe_filename


@router.post("/image")
async def upload_image(file: UploadFile = File(...)):
    """上传单张图片，返回URL"""
    safe_filename = _validate_and_save(file)
    return {
        "url": f"/static/uploads/{safe_filename}",
        "filename": safe_filename,
    }


@router.post("/images")
async def upload_images(files: list[UploadFile] = File(...)):
    """批量上传图片（最多5张）"""
    results = []
    for file in files[:5]:
        try:
            safe_filename = _validate_and_save(file)
            results.append({
                "url": f"/static/uploads/{safe_filename}",
                "filename": safe_filename,
            })
        except HTTPException:
            # 单张失败不影响其他
            continue
    return {"items": results}
