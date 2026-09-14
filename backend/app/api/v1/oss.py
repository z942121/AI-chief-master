import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException
from dotenv import load_dotenv
import oss2

load_dotenv()

router = APIRouter(prefix="/oss", tags=["OSS文件上传"])

OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID")
OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET")
OSS_BUCKET = os.getenv("OSS_BUCKET")
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT")

auth = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
bucket = oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "bmp", "webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024
PRE_SIGN_URL_EXPIRES = 3600


def _get_file_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def _generate_oss_key(filename: str, folder: str = "uploads") -> str:
    ext = _get_file_extension(filename)
    timestamp = datetime.now().strftime("%Y%m%d")
    unique_id = uuid.uuid4().hex[:12]
    if ext:
        return f"{folder}/{timestamp}/{unique_id}.{ext}"
    return f"{folder}/{timestamp}/{unique_id}"


def _get_content_type(filename: str) -> str:
    ext = _get_file_extension(filename)
    content_types = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "webp": "image/webp",
    }
    return content_types.get(ext, "application/octet-stream")


@router.post("/upload", summary="上传文件到阿里云OSS")
async def upload_file(file: UploadFile = File(...), folder: Optional[str] = "uploads"):
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = _get_file_extension(file.filename)
    if ext and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")

    file_content = await file.read()
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"文件大小超过限制，最大为 {MAX_FILE_SIZE // (1024*1024)} MB")

    oss_key = _generate_oss_key(file.filename, folder)
    content_type = _get_content_type(file.filename)

    try:
        bucket.put_object(
            oss_key,
            file_content,
            headers={"Content-Type": content_type}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传文件到OSS失败: {str(e)}")

    file_url = bucket.sign_url('GET', oss_key, PRE_SIGN_URL_EXPIRES, slash_safe=True)

    return {
        "code": 200,
        "message": "上传成功",
        "data": {
            "oss_key": oss_key,
            "file_url": file_url,
            "filename": file.filename,
            "size": len(file_content),
            "content_type": content_type,
            "expires_in": PRE_SIGN_URL_EXPIRES
        }
    }


@router.get("/presign-url", summary="获取文件预签名URL")
async def get_presign_url(oss_key: str, expires: Optional[int] = PRE_SIGN_URL_EXPIRES):
    if not oss_key:
        raise HTTPException(status_code=400, detail="oss_key不能为空")

    if expires < 60 or expires > 604800:
        raise HTTPException(status_code=400, detail="有效期必须在60秒到604800秒（7天）之间")

    try:
        file_url = bucket.sign_url('GET', oss_key, expires, slash_safe=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成预签名URL失败: {str(e)}")

    return {
        "code": 200,
        "message": "获取成功",
        "data": {
            "oss_key": oss_key,
            "file_url": file_url,
            "expires_in": expires
        }
    }
