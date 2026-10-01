import os
import secrets
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Header, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

app = FastAPI(title="Walid AI Edit")

API_KEY = os.getenv("API_KEY", "")


@app.get("/")
def home():
    return {"app": "Walid AI Edit", "status": "online"}


@app.post("/edit")
async def edit_video(
    video: UploadFile = File(...),
    style: str = "normal",
    x_api_key: str = Header(default="")
):
    if not API_KEY or not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="Clé API invalide")

    allowed_styles = {"normal", "fast", "mirror", "gray"}
    if style not in allowed_styles:
        raise HTTPException(status_code=400, detail="Style inconnu")

    if not video.filename or not video.filename.lower().endswith(
        (".mp4", ".mov", ".mkv", ".webm")
    ):
        raise HTTPException(status_code=400, detail="Format vidéo non pris en charge")

    temp_dir = tempfile.mkdtemp(prefix="walid_")
    input_path = Path(temp_dir) / "input_video"
    output_path = Path(temp_dir) / "edited.mp4"

    try:
        size = 0
        with open(input_path, "wb") as f:
            while True:
                chunk = await video.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > 50 * 1024 * 1024:
                    raise HTTPException(
                        status_code=413,
                        detail="Vidéo limitée à 50 Mo pour ce test"
                    )
                f.write(chunk)

        filters = []
        audio_filters = []

        if style == "fast":
            filters.append("setpts=0.75*PTS")
            audio_filters.append("atempo=1.333333")
        elif style == "mirror":
            filters.append("hflip")
        elif style == "gray":
            filters.append("hue=s=0")

        command = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-vf", ",".join(filters) if filters else "null",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-crf", "25", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k"
        ]

        if audio_filters:
            command += ["-af", ",".join(audio_filters)]

        command += ["-movflags", "+faststart", str(output_path)]

        result = subprocess.run(
            command, capture_output=True, text=True, timeout=180
        )

        if result.returncode != 0 or not output_path.exists():
            raise HTTPException(
                status_code=422,
                detail="Montage impossible. Essaie une petite vidéo MP4."
            )

        def cleanup():
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

        return FileResponse(
            str(output_path),
            media_type="video/mp4",
            filename="walid_ai_edit.mp4",
            background=BackgroundTask(cleanup)
        )

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Montage trop long")
    except Exception:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    finally:
        await video.close()
  
