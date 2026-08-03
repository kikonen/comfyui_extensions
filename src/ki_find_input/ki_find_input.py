# ki_find_input.py

import os
import re

import ipaddress
import mimetypes
import socket
import tempfile
from urllib.parse import urlparse

import numpy as np
import requests
import torch
import av
from PIL import Image
import folder_paths

import comfy.utils
from comfy.model_patcher import ModelPatcher  # optional if you need to patch models

ALLOWED_IMAGE_MIMES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}

ALLOWED_AUDIO_MIMES = {
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "audio/flac",
    "audio/ogg",
    "audio/x-flac",
    "audio/mp4",
}

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"}

# ------------------------------------------------------------------
def _is_blocked_ip(hostname: str) -> bool:
    return False

    try:
        infos = socket.getaddrinfo(hostname, None)
    except Exception:
        return True

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue

        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return True
    return False

# ------------------------------------------------------------------
def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    # Accept http/https with host
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        if _is_blocked_ip(parsed.hostname):
            raise ValueError("Refusing to access private or invalid host")
        return url
    # Accept file:// or local paths (absolute or relative to ComfyUI input dir)
    if parsed.scheme == "file":
        path = parsed.path
    elif parsed.scheme == "" and parsed.netloc == "":
        # First try as-is, then relative to input directory
        if os.path.exists(url):
            path = url
        else:
            candidate = os.path.join(folder_paths.get_input_directory(), url)
            path = candidate if os.path.exists(candidate) else url
    else:
        raise ValueError("URL must be http/https with a host or an existing local path")
    if not os.path.exists(path):
        raise ValueError(f"Local file not found: {path}")
    return path


# ------------------------------------------------------------------
def _download_to_temp(url: str, max_bytes: int, timeout: tuple[float, float]):
    headers = {
        "User-Agent": "ComfyUI-DownloadFile/1.0 (+https://github.com/serious-factory/ComfyUI-DownloadFile)"
    }
    response = requests.get(url, stream=True, timeout=timeout, allow_redirects=True, headers=headers)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    suffix = ""
    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[1].lower()
    if ext:
        suffix = ext
    else:
        guessed = mimetypes.guess_extension(content_type) if content_type else None
        if guessed:
            suffix = guessed

    temp_dir = folder_paths.get_temp_directory()
    temp_file = tempfile.NamedTemporaryFile(dir=temp_dir, delete=False, suffix=suffix or "")
    temp_path = temp_file.name
    written = 0

    try:
        for chunk in response.iter_content(chunk_size=8192):
            if not chunk:
                continue
            written += len(chunk)
            if written > max_bytes:
                raise ValueError("File exceeds allowed size limit")
            temp_file.write(chunk)
    finally:
        temp_file.close()
        if written == 0:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise ValueError("Empty response body")

    try:
        folder_paths.add_temp_file(os.path.basename(temp_path))
    except Exception:
        # Non-fatal; continue even if registration fails
        pass

    return temp_path, content_type

# ------------------------------------------------------------------
def _download_to_temp(url: str, max_bytes: int, timeout: tuple[float, float]):
    headers = {
        "User-Agent": "ComfyUI-DownloadFile/1.0 (+https://github.com/serious-factory/ComfyUI-DownloadFile)"
    }
    response = requests.get(url, stream=True, timeout=timeout, allow_redirects=True, headers=headers)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    suffix = ""
    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[1].lower()
    if ext:
        suffix = ext
    else:
        guessed = mimetypes.guess_extension(content_type) if content_type else None
        if guessed:
            suffix = guessed

    temp_dir = folder_paths.get_temp_directory()
    temp_file = tempfile.NamedTemporaryFile(dir=temp_dir, delete=False, suffix=suffix or "")
    temp_path = temp_file.name
    written = 0

    try:
        for chunk in response.iter_content(chunk_size=8192):
            if not chunk:
                continue
            written += len(chunk)
            if written > max_bytes:
                raise ValueError("File exceeds allowed size limit")
            temp_file.write(chunk)
    finally:
        temp_file.close()
        if written == 0:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise ValueError("Empty response body")

    try:
        folder_paths.add_temp_file(os.path.basename(temp_path))
    except Exception:
        # Non-fatal; continue even if registration fails
        pass

    return temp_path, content_type

# ----------------------------------------------------------------------
def _load_image(path: str):
    with Image.open(path) as img:
        rgb = img.convert("RGB")
        array = np.asarray(rgb).astype(np.float32) / 255.0
        tensor = torch.from_numpy(array).unsqueeze(0)
    return tensor

# ----------------------------------------------------------------------
def _load_audio(path: str):
    with av.open(path) as af:
        if not af.streams.audio:
            raise ValueError("No audio stream found in the file.")

        stream = af.streams.audio[0]
        sample_rate = stream.codec_context.sample_rate
        channels = stream.channels

        frames = []
        for frame in af.decode(streams=stream.index):
            buf = torch.from_numpy(frame.to_ndarray())
            if buf.shape[0] != channels:
                buf = buf.view(-1, channels).t()
            frames.append(buf)

        if not frames:
            raise ValueError("No audio frames decoded.")

        waveform = torch.cat(frames, dim=1)
        if waveform.dtype.is_floating_point:
            waveform = waveform.float()
        elif waveform.dtype == torch.int16:
            waveform = waveform.float() / (2 ** 15)
        elif waveform.dtype == torch.int32:
            waveform = waveform.float() / (2 ** 31)
        else:
            raise ValueError(f"Unsupported wav dtype: {waveform.dtype}")

    return {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}

# ----------------------------------------------------------------------
# Define the node class ------------------------------------------
class KIFindInputNode:
    """
    Scan the ComfyUI `inupts` folder and return files whose names match
    a supplied regex or glob pattern.

    Based into
    https://github.com/serious-factory/ComfyUI-DownloadFile/blob/main/download_nodes/downloader.py

    /api/v1/files/1fbb847b-f182-4135-8a2b-a5be62db9001/content

    Parameters
    ----------
    image_url     : str
        Original content image
    """
    @classmethod
    def INPUT_TYPES(s):
        # Node UI: these fields appear in the editor
        return {
            "required": {
                "image_url": ("STRING", {"default": "random_uuid"}),
            }
        }


    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "find_input"
    CATEGORY = "utils"

    # ------------------------------------------------------------------
    def find_input(self, image_url: str, base_folder: str = "input"):
        result = self.find_input(image_url, base_folder)
        if result[0]:
            return (result[1],)

        return self._download_file(image_url):

    # ------------------------------------------------------------------
    def _fetch_input(self, image_url: str, base_folder: str = "input"):
        comfy_root = self._find_root_dir()

        parts = image_url.split("/")
        print(f"parts={', '.join(parts)}")

        for part in parts:
            if len(part) < 12:
                continue

            pattern = f"*{part}*"
            print(f"try={pattern}")

            matches = self._match_input_files(pattern, True, base_folder)

            print(f"matches={', '.join(matches)}")
            if len(matches) > 0:
                print(f"OK: pattern{pattern}, result={matches[0]}")
                return (True, _load_image(matches[0]),)
            else:
                print(f"KO: pattern= {pattern}")

        print(f"KO: image={image_url} - nothing found")
        empty_image = torch.zeros((1, 1, 1, 3), dtype=torch.float32)

        return (False, empty_image,)

    # ------------------------------------------------------------------
    # Resolve the full path (Comfy root + folder)
    def _find_root_dir(self):
        # 3 levels up
        comfy_root = os.path.abspath(os.path.join(__file__, "..", "..", ".."))
        print(f"comfy_root={comfy_root}")

        return comfy_root

    # ------------------------------------------------------------------
    def _match_input_files(self, pattern: str, return_full_path: bool, base_folder: str = "input"):
        comfy_root = self._find_root_dir()
        target_dir = os.path.normpath(os.path.join(comfy_root, base_folder))

        print(f"target_dir={target_dir}")

        if not os.path.isdir(target_dir):
            raise FileNotFoundError(f"Directory {target_dir} does not exist")

        # Decide whether we interpret the pattern as glob or regex
        is_regex = pattern.startswith("re:")
        if is_regex:
            regex_pat = re.compile(pattern[3:])  # strip 're:' prefix
        else:
            # Simple glob → convert to regex
            import fnmatch, pathlib
            # fnmatch.translate returns a regex string
            regex_pat = re.compile(fnmatch.translate(pattern))

        matches: List[str] = []

        for root, _, files in os.walk(target_dir):
            for fname in files:
                if regex_pat.search(fname):
                    rel_path = os.path.relpath(os.path.join(root, fname), comfy_root)
                    matches.append(
                        os.path.normpath(rel_path) if not return_full_path else os.path.abspath(os.path.join(root, fname))
                    )

        return matches

    # ------------------------------------------------------------------
    def _download_file(self, url, expect_type="auto", max_mb=50):
        empty_image = torch.zeros((1, 1, 1, 3), dtype=torch.float32)
        empty_audio = {"waveform": torch.zeros((1, 1, 1)), "sample_rate": 44100}

        safe_url = _validate_url(url)
        timeout = (5.0, 15.0)
        max_bytes = max_mb * 1024 * 1024
        try:
            if safe_url.startswith("http"):
                temp_path, content_type = _download_to_temp(safe_url, max_bytes=max_bytes, timeout=timeout)
            else:
                # Local file path
                temp_path = safe_url
                content_type = mimetypes.guess_type(temp_path)[0] or ""
        except Exception as e:
            raise ValueError(f"DownloadFile error: {e}")

        ext = os.path.splitext(temp_path)[1].lower()

        def is_image():
            if expect_type == "image":
                return True
            if content_type in ALLOWED_IMAGE_MIMES:
                return True
            return ext in ALLOWED_IMAGE_EXTS

        def is_audio():
            if expect_type == "audio":
                return True
            if content_type in ALLOWED_AUDIO_MIMES:
                return True
            return ext in ALLOWED_AUDIO_EXTS

        if is_image():
            image = _load_image(temp_path)
            return (image, empty_audio, temp_path, content_type or "")

        if is_audio():
            audio = _load_audio(temp_path)
            return (empty_image, audio, temp_path, content_type or "")

        raise ValueError("Unsupported file type; only image/audio are allowed")


# ----------------------------------------------------------------------
# 2️⃣  Register the node with ComfyUI ---------------------------------
NODE_CLASS_MAPPINGS = {
    "KIFindInput": KIFindInputNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "KIFindInput": "KI Find Input",
}
