"""Versioned, validated ZIP backup of station ROI, reference PNGs and detector settings.

Archive contents are data-only. Administrator credentials and tokens are never
exported. Imports validate every byte before any live file is replaced.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import struct
import tempfile
import zipfile
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from .station_position import STAGES, MAX_REFS, StageProfileStore
from .user_access import LocalUserAccess
from .water_session import CalibrationInput, DetectorSettings, InvalidFrame

FORMAT = "zebovision-device-profile"
FORMAT_VERSION = 1
MAX_ZIP_BYTES = 600 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 600 * 1024 * 1024
MAX_IMAGE_BYTES = 30 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def _data(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def _normalise_profile(raw: object) -> tuple[dict, dict[str, tuple[int, int]]]:
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise InvalidFrame("设备配置版本不受支持")
    stages = raw.get("stages")
    if not isinstance(stages, dict) or set(stages) != set(STAGES):
        raise InvalidFrame("设备配置缺少 P1/P2/P3 工位")
    normalized: dict = {"version": 1, "stages": {}}
    image_sizes: dict[str, tuple[int, int]] = {}
    for stage in STAGES:
        entry = stages[stage]
        if not isinstance(entry, dict):
            raise InvalidFrame("工位配置格式错误")
        original_cal = entry.get("calibration")
        cal = None if original_cal is None else CalibrationInput.model_validate(original_cal).model_dump()
        if cal is not None:
            if not all(math.isfinite(cal[k]) for k in ("cx", "cy", "radius")):
                raise InvalidFrame("标定坐标无效")
            if cal["width"] * cal["height"] > 4_194_304:
                raise InvalidFrame("参考图像分辨率超限")
        refs = entry.get("references")
        if not isinstance(refs, list) or len(refs) > MAX_REFS:
            raise InvalidFrame("参考帧数量超限")
        if refs and cal is None:
            raise InvalidFrame("参考帧缺少对应 ROI 标定")
        out_refs = []
        for ref in refs:
            if not isinstance(ref, dict) or not ID_PATTERN.fullmatch(str(ref.get("id", ""))):
                raise InvalidFrame("参考帧 ID 不合法")
            ident = ref["id"]
            if ident in image_sizes:
                raise InvalidFrame("参考帧 ID 重复")
            group = ref.get("group", "nozzle_a" if stage == "P3" else "default")
            if group not in (("nozzle_a", "nozzle_b") if stage == "P3" else ("default",)):
                raise InvalidFrame("参考帧喷头分组无效")
            name = ref.get("source")
            if (not isinstance(name, str) or not 1 <= len(name) <= 255
                    or "/" in name or "\\" in name or any(ord(ch) < 32 for ch in name)):
                raise InvalidFrame("参考视频文件名无效")
            time_s = ref.get("time_s")
            if (not isinstance(time_s, (int, float)) or isinstance(time_s, bool)
                    or not math.isfinite(time_s) or not 0 <= time_s <= 86400):
                raise InvalidFrame("参考帧时间无效")
            out_refs.append({"id": ident, "time_s": time_s,
                             "source": name, "group": group})
            image_sizes[ident] = (cal["width"], cal["height"])
        normalized["stages"][stage] = {"calibration": cal, "references": out_refs}
    return normalized, image_sizes


def _validate_archive(source: Path) -> tuple[dict, DetectorSettings, dict[str, bytes]]:
    if source.suffix.lower() != ".zip" or not source.is_file():
        raise InvalidFrame("请选择存在的 ZIP 配置文件")
    if source.stat().st_size > MAX_ZIP_BYTES:
        raise InvalidFrame("配置压缩包过大")
    try:
        with zipfile.ZipFile(source, "r") as archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if len(names) != len(set(names)) or len(names) > 39:
                raise InvalidFrame("ZIP 文件列表不合法")
            if any(i.is_dir() or i.file_size > MAX_IMAGE_BYTES or
                   i.flag_bits & 1 for i in infos):
                raise InvalidFrame("ZIP 含不支持的文件")
            if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
                raise InvalidFrame("ZIP 解压数据过大")
            required = {"manifest.json", "stations/profile.json", "detector/settings.json"}
            if not required.issubset(names):
                raise InvalidFrame("ZIP 缺少设备配置文件")
            for name in required:
                if archive.getinfo(name).file_size > 128 * 1024:
                    raise InvalidFrame("ZIP 配置文本过大")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest != {"format": FORMAT, "version": FORMAT_VERSION}:
                raise InvalidFrame("ZIP 设备配置格式或版本不匹配")
            profile, sizes = _normalise_profile(json.loads(archive.read("stations/profile.json")))
            settings = DetectorSettings.model_validate(json.loads(archive.read("detector/settings.json")))
            expected = required | {f"stations/references/{ident}.png" for ident in sizes}
            if set(names) != expected:
                raise InvalidFrame("ZIP 缺少参考帧或包含多余文件")
            images = {}
            for ident, (width, height) in sizes.items():
                raw = archive.read(f"stations/references/{ident}.png")
                # Check PNG IHDR dimensions before allowing OpenCV to allocate
                # image memory; the ZIP file may come from an untrusted device.
                if (len(raw) < 24 or not raw.startswith(PNG_SIGNATURE)
                        or struct.unpack(">II", raw[16:24]) != (width, height)):
                    raise InvalidFrame("参考帧 PNG 格式或分辨率不匹配")
                images[ident] = raw
            return profile, settings, images
    except (zipfile.BadZipFile, zipfile.LargeZipFile, json.JSONDecodeError,
            UnicodeDecodeError, KeyError, ValidationError, OSError, EOFError) as exc:
        raise InvalidFrame("ZIP 配置文件已损坏或内容不合法") from exc


def export_profile_archive(store: StageProfileStore, access: LocalUserAccess,
                           admin_token: str, destination: str) -> dict:
    settings = access.approved_settings(admin_token)
    target = Path(destination)
    if target.suffix.lower() != ".zip" or not target.parent.is_dir():
        raise InvalidFrame("请选择有效的 ZIP 保存位置")
    with store._lock:
        profile, image_sizes = _normalise_profile(store.snapshot())
        temp = target.parent / ("." + uuid4().hex + ".zip")
        try:
            with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=6, allowZip64=True) as archive:
                archive.writestr("manifest.json", _data({"format": FORMAT, "version": FORMAT_VERSION}))
                archive.writestr("stations/profile.json", _data(profile))
                archive.writestr("detector/settings.json", _data(settings.model_dump()))
                for ident in image_sizes:
                    reference = store.root / (ident + ".png")
                    if not reference.is_file():
                        raise InvalidFrame("参考帧文件缺失，无法导出完整配置")
                    archive.write(reference, f"stations/references/{ident}.png")
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
    return {"saved": True, "reference_count": len(image_sizes)}


def import_profile_archive(store: StageProfileStore, access: LocalUserAccess,
                           admin_token: str, source: str) -> dict:
    # Check authorization before reading an arbitrary user-selected file.
    access.approved_settings(admin_token)
    profile, settings, images = _validate_archive(Path(source))
    with store._lock:
        root = store.root
        staging = Path(tempfile.mkdtemp(prefix="stations-stage-", dir=root.parent))
        backup = root.parent / ("stations-backup-" + uuid4().hex)
        activated = False
        backed_up = False
        previous_profile = store._profile
        try:
            (staging / "profile.json").write_bytes(_data(profile))
            for ident, raw in images.items():
                (staging / (ident + ".png")).write_bytes(raw)
            # The existing profile remains intact until every archive entry
            # has been validated and written into the staging directory.
            os.replace(root, backup)
            backed_up = True
            os.replace(staging, root)
            activated = True
            access.update_settings(admin_token, settings)
            store._profile = profile
        except Exception:
            if activated:
                shutil.rmtree(root)
            if backed_up:
                os.replace(backup, root)
            store._profile = previous_profile
            raise
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        # Old profiles are removed only after both ROI and detector settings
        # have been committed. A failed import rolls back to the old setup.
        shutil.rmtree(backup)
        return {"profile": store.snapshot(), "settings": settings.model_dump(),
                "reference_count": len(images)}
