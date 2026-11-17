import re
import uuid
from pathlib import Path

import config

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_name(filename: str) -> str:
    """Удаляет путь и заменяет небезопасные символы в имени файла."""
    filename = filename.replace("\\", "/").split("/")[-1]
    filename = _SAFE_NAME_RE.sub("_", filename).strip("._")
    return (filename or "file")[:200]


class Storage:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _entry_dir(self, file_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", file_id):
            raise ValueError("Некорректный идентификатор файла")
        return self.data_dir / file_id

    async def save_upload(self, original_name, upload_file) -> dict:
        """Сохраняет загрузку порциями, не читая весь файл в RAM."""
        file_id = uuid.uuid4().hex
        safe_name = _sanitize_name(original_name)
        entry = self._entry_dir(file_id)
        entry.mkdir()
        content_path = entry / "content.bin"
        total_size = 0

        try:
            with content_path.open("wb") as output:
                while chunk := await upload_file.read(config.UPLOAD_CHUNK_SIZE):
                    total_size += len(chunk)
                    if total_size > config.MAX_FILE_SIZE:
                        raise ValueError(
                            f"Размер файла превышает лимит {config.MAX_FILE_SIZE // (1024 * 1024)} МБ"
                        )
                    output.write(chunk)

            (entry / "meta.txt").write_text(safe_name, encoding="utf-8")
        except Exception:
            if content_path.exists():
                content_path.unlink()
            if entry.exists():
                entry.rmdir()
            raise

        return {"id": file_id, "name": safe_name, "size": total_size}

    def list_files(self) -> list[dict]:
        result = []
        for entry in self.data_dir.iterdir():
            if not entry.is_dir() or not re.fullmatch(r"[0-9a-f]{32}", entry.name):
                continue
            meta = entry / "meta.txt"
            content = entry / "content.bin"
            if meta.exists() and content.exists():
                result.append({
                    "id": entry.name,
                    "name": meta.read_text(encoding="utf-8"),
                    "size": content.stat().st_size,
                })
        return sorted(result, key=lambda item: item["name"].lower())

    def get_paths(self, file_id: str) -> tuple[Path, str]:
        entry = self._entry_dir(file_id)
        meta = entry / "meta.txt"
        content = entry / "content.bin"
        if not meta.is_file() or not content.is_file():
            raise FileNotFoundError(file_id)
        return content, meta.read_text(encoding="utf-8")

    def delete(self, file_id: str):
        entry = self._entry_dir(file_id)
        content = entry / "content.bin"
        meta = entry / "meta.txt"
        if not content.is_file() or not meta.is_file():
            raise FileNotFoundError(file_id)
        content.unlink()
        meta.unlink()
        entry.rmdir()
