"""Audio upload and speech-to-text endpoint for PsyConsult."""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.app_config.settings import settings
from app.portal.router import actor_id as require_chat_identity

router = APIRouter()
logger = logging.getLogger("clinical_cds.transcribe")

# Qwen3-ASR-Flash accepts audio up to 5 minutes and 10 MB after encoding.
# Keep the raw upload below 7 MiB to leave room for Base64/JSON overhead.
MAX_AUDIO_BYTES = 7 * 1024 * 1024
ALLOWED_MIME_TYPES = {
    "audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav",
    "audio/x-wav", "audio/aac", "audio/opus",
}
EXTENSION_MIME_TYPES = {
    ".webm": "audio/webm", ".ogg": "audio/ogg", ".mp4": "audio/mp4",
    ".m4a": "audio/mp4", ".wav": "audio/wav", ".mp3": "audio/mpeg",
    ".aac": "audio/aac", ".opus": "audio/opus",
}


def _api_key() -> str:
    value = getattr(settings, "dashscope_api_key", None)
    if hasattr(value, "get_secret_value"):
        value = value.get_secret_value()
    return str(value or "").strip()


def _endpoint() -> str:
    """Use an explicit ASR endpoint, or the existing DashScope-compatible URL."""
    configured = os.getenv("ASR_API_BASE_URL", "").strip()
    if not configured:
        model_base = str(getattr(settings, "base_url", "") or "").strip()
        if "dashscope.aliyuncs.com" in model_base or ".maas.aliyuncs.com" in model_base:
            configured = model_base
        else:
            configured = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    configured = configured.rstrip("/")
    if configured.endswith("/chat/completions"):
        return configured
    return configured + "/chat/completions"


def _mime_type(content_type: str | None, filename: str | None) -> str | None:
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime == "audio/x-wav":
        return "audio/wav"
    if mime in ALLOWED_MIME_TYPES:
        return mime
    if mime in {"", "application/octet-stream"}:
        return EXTENSION_MIME_TYPES.get(Path(filename or "").suffix.lower())
    return None


def _extract_transcript(payload: dict[str, Any]) -> str:
    """Parse the OpenAI-compatible Qwen ASR response without exposing raw payloads."""
    choices = payload.get("choices") or []
    if choices:
        message = (choices[0] or {}).get("message") or {}
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            return "".join(parts).strip()

    # Defensive fallback for compatible deployments that wrap the transcript.
    output = payload.get("output") or {}
    nested = output.get("output") or {}
    sentence = nested.get("sentence") or {}
    text = sentence.get("text") or output.get("text") or ""
    return text.strip() if isinstance(text, str) else ""


@router.post("/transcribe")
async def transcribe_audio(
    user_id: Annotated[str, Depends(require_chat_identity)],
    file: UploadFile = File(...),
) -> dict[str, str]:
    """Transcribe one short audio recording; audio is not persisted by this API."""
    mime = _mime_type(file.content_type, file.filename)
    if mime is None:
        await file.close()
        raise HTTPException(
            status_code=415,
            detail="不支持的音频格式，请使用浏览器录音生成的 WebM/OGG/MP4 音频。",
        )

    try:
        audio_bytes = await file.read(MAX_AUDIO_BYTES + 1)
    finally:
        await file.close()

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="录音文件为空，请重新录制。")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail="录音文件过大，请缩短录音时间后重试（单次录音最长约 5 分钟）。",
        )

    key = _api_key()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="尚未配置 DashScope API Key，暂时无法进行语音识别。",
        )

    data_uri = f"data:{mime};base64,{base64.b64encode(audio_bytes).decode('ascii')}"
    request_body = {
        "model": "qwen3-asr-flash",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": data_uri},
                    }
                ],
            }
        ],
        "stream": False,
        "asr_options": {"language": "zh", "enable_itn": True},
    }

    try:
        # Avoid inheriting malformed SOCKS proxy variables from local shells.
        # Set ASR_API_BASE_URL in the environment when using a workspace-specific endpoint.
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(90.0, connect=10.0), trust_env=False
        ) as client:
            response = await client.post(
                _endpoint(),
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
            )

        if response.status_code >= 400:
            logger.warning(
                "asr_provider_http_error user_id=%s status=%s",
                user_id,
                response.status_code,
            )
            raise HTTPException(
                status_code=502,
                detail="语音识别服务暂时不可用，请检查服务配置或稍后重试。",
            )
        result = response.json()
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        logger.warning("asr_provider_timeout user_id=%s", user_id)
        raise HTTPException(
            status_code=504, detail="语音识别超时，请缩短录音后重试。"
        ) from exc
    except Exception as exc:
        logger.exception("asr_request_failed user_id=%s", user_id)
        raise HTTPException(
            status_code=502, detail="语音识别失败，请检查网络和 ASR 服务配置后重试。"
        ) from exc

    transcript = _extract_transcript(result if isinstance(result, dict) else {})
    if not transcript:
        logger.warning("asr_empty_transcript user_id=%s", user_id)
        raise HTTPException(
            status_code=502, detail="没有识别到清晰语音，请靠近麦克风后重新录制。"
        )

    # Do not log transcript/audio contents. The frontend asks the user to review it.
    logger.info(
        "asr_transcription_completed user_id=%s chars=%d",
        user_id,
        len(transcript),
    )
    return {"text": transcript}
