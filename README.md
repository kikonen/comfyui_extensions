# ComfyUI extensions

## Plugins

### ki_find_input

Workaround for Open WebUI vs Comfy edit image integration

Since all these fail
- passing via Load Image
- passing url
- passing image encode as base64

This workaround exists. "uploads" of open webui is mapped to comfyui side
and used as input to allow accessing data directly from it. However, that
is not enough since content data is passed with url paths to "content",
thus those are mapped to files in "uploads/input".

### Expected setup

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    volumes:
      - ./ollama_data:/root/.ollama
    ports:
      - "8106:11434"
    environment:
      - OLLAMA_API_KEY=${OLLAMA_API_KEY}
      - OLLAMA_NUM_CTX=262144
      - OLLAMA_HOST=0.0.0.0
      - OLLAMA_NUM_PARALLEL=1
      - OLLAMA_KEEP_ALIVE=30m
      - OLLAMA_FLASH_ATTENTION=1
      - OLLAMA_MAX_LOADED_MODELS=1
      - OLLAMA_KV_CACHE_TYPE=q8_0
      - OLLAMA_CONTEXT_LENGTH=262144
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    volumes:
      - ./open-webui_data:/app/backend/data
    ports:
      - "8107:8080"
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
      - OPENWEBUI_BASE_URL=http://open-webui:8107
      - COMFYUI_BASE_URL=http://comfyui:8188
      - WEBUI_SECRET_KEY=${WEBUI_SECRET_KEY}
      - ENABLE_SIGNUP=${ENABLE_SIGNUP}
      - USER_PERMISSIONS_FEATURES_WEB_SEARCH=${USER_PERMISSIONS_FEATURES_WEB_SEARCH}
      - ENV=prod
    restart: unless-stopped
    depends_on:
      - ollama

  comfyui:
    image: yanwk/comfyui-boot:cu128-slim
    container_name: comfyui
    ports:
      - "8108:8188"
    volumes:
      - ./comfyui_data/storage:/root/ComfyUI
      - ./comfyui_data/models:/root/ComfyUI/models
      - ./comfyui_data/output:/root/ComfyUI/output
      # JAETTU VOLUME: Linkittää Open WebUI:n lataukset ComfyUI:n input-kansioksi
      - ./open-webui_data/uploads:/root/ComfyUI/input
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

### References
- https://github.com/serious-factory/ComfyUI-DownloadFile/blob/main/download_nodes/downloader.py

## References

- https://comfy.org
- https://github.com/Comfy-Org/ComfyUI
- https://docs.openwebui.com/features/chat-conversations/image-generation-and-editing/comfyui/#edit-image
- https://www.reddit.com/r/OpenWebUI/comments/1q3qtwj/edit_image_with_comfyui/
