# ki_find_input.py

import os
import re

import numpy as np
import requests
import torch
import av
from PIL import Image
import folder_paths

import comfy.utils
from comfy.model_patcher import ModelPatcher  # optional if you need to patch models

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

    def find_input(self, image_url: str, base_folder: str = "input"):
        comfy_root = self._find_root_dir()

        parts = image_url.split("/")
        print(f"parts={', '.join(parts)}")

        for part in parts:
            if len(part) < 12:
                continue

            pattern = f"*{part}*"
            print(f"try={pattern}")

            matches = self._match_files(pattern, True, base_folder)

            print(f"matches={', '.join(matches)}")
            if len(matches) > 0:
                print(f"OK: pattern{pattern}, result={matches[0]}")
                return (self._load_image(matches[0]),)
            else:
                print(f"KO: pattern= {pattern}")

        print(f"KO: image={image_url} - nothing found")
        empty_image = torch.zeros((1, 1, 1, 3), dtype=torch.float32)

        return (empty_image,)

    # ------------------------------------------------------------------
    def _load_image(self, path: str):
        with Image.open(path) as img:
            rgb = img.convert("RGB")
            array = np.asarray(rgb).astype(np.float32) / 255.0
            tensor = torch.from_numpy(array).unsqueeze(0)
        return tensor

    # ------------------------------------------------------------------
    # Resolve the full path (Comfy root + folder)
    def _find_root_dir():
        # 3 levels up
        comfy_root = os.path.abspath(os.path.join(__file__, "..", "..", ".."))
        print(f"comfy_root={comfy_root}")

        return comfy_root

    # ------------------------------------------------------------------
    def _match_files(self, pattern: str, return_full_path: bool, base_folder: str = "input"):
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

# ----------------------------------------------------------------------
# 2️⃣  Register the node with ComfyUI ---------------------------------
NODE_CLASS_MAPPINGS = {
    "KIFindInput": KIFindInputNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "KIFindInput": "KI Find Input",
}
