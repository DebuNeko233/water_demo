"""Administrator-owned source selector. RTSP credentials stay on this machine.

The running source is chosen in Python, never from an operator-supplied URL.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
from typing import Literal

import cv2
from pydantic import BaseModel, Field, model_validator

from sample_backend.core.config import data_directory
from .water_session import InvalidFrame


class VideoSourceSettings(BaseModel):
    kind: Literal['file', 'rtsp', 'usb'] = 'file'
    rtsp_url: str = Field(default='', max_length=2048)
    usb_index: int = Field(default=0, ge=0, le=15)
    file_path: str = Field(default='', max_length=4096)

    @model_validator(mode='after')
    def check_source(self):
        if self.kind == 'file' and self.file_path:
            from .video_stream import VIDEO_SUFFIXES
            target = Path(self.file_path)
            if not target.is_absolute() or target.suffix.lower() not in VIDEO_SUFFIXES:
                raise ValueError('本地视频路径或格式无效')
        if self.kind == 'rtsp':
            try:
                parsed = urlsplit(self.rtsp_url)
                if (parsed.scheme.lower() != 'rtsp' or not parsed.hostname
                        or parsed.port is not None and not (1 <= parsed.port <= 65535)
                        or any(ord(ch) < 32 for ch in self.rtsp_url)
                        or '\\' in self.rtsp_url):
                    raise ValueError('RTSP 地址须以 rtsp:// 开头，并包含合法的主机')
            except ValueError as exc:
                raise ValueError('请输入有效的 RTSP 地址') from exc
        return self


class VideoSourceStore:
    def __init__(self, path: Path | None = None):
        self.path = path or data_directory() / 'video' / 'source.json'
        self._lock = threading.RLock()
        self._source = VideoSourceSettings()
        if self.path.is_file():
            self._source = VideoSourceSettings.model_validate_json(
                self.path.read_text(encoding='utf-8'))

    def current(self) -> VideoSourceSettings:
        with self._lock:
            return self._source.model_copy()

    def public(self) -> dict:
        with self._lock:
            source = self._source
            # Never leak URL username/password or camera host to an operator.
            return {'kind': source.kind, 'usb_index': source.usb_index}

    def save(self, settings: VideoSourceSettings) -> VideoSourceSettings:
        with self._lock:
            if settings.kind == 'file' and settings.file_path:
                if not Path(settings.file_path).is_file():
                    raise InvalidFrame('所选本地视频不存在')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(uuid4().hex + '.tmp')
            try:
                descriptor = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
                    output.write(settings.model_dump_json(indent=2))
                os.replace(tmp, self.path)
            finally:
                tmp.unlink(missing_ok=True)
            self._source = settings.model_copy()
            return self.current()


def open_capture(source: VideoSourceSettings, file_path: str = '') -> cv2.VideoCapture:
    """Use only the configured capture class; no arbitrary filesystem/device URL."""
    if source.kind == 'file':
        from .video_stream import VIDEO_SUFFIXES
        target = Path(source.file_path or file_path)
        if not target.is_file() or target.suffix.lower() not in VIDEO_SUFFIXES:
            raise InvalidFrame('请选择本地视频文件')
        cap = cv2.VideoCapture(str(target))
    elif source.kind == 'rtsp':
        # CAP_FFMPEG is preferred for RTSP, and OpenCV can fall back if it
        # wasn't compiled with that backend.
        cap = cv2.VideoCapture(source.rtsp_url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(source.rtsp_url)
    else:
        cap = cv2.VideoCapture(source.usb_index, cv2.CAP_DSHOW) if os.name == 'nt' else cv2.VideoCapture(source.usb_index)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(source.usb_index)
    if not cap.isOpened():
        cap.release()
        raise InvalidFrame('视频源连接失败，请检查摄像头、RTSP 地址或驱动')
    if source.kind != 'file':
        # Some drivers ignore buffer size; do not claim a hard latency bound.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap
