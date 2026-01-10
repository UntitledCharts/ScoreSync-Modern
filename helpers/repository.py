from helpers.sha1 import calculate_sha1

from typing import Optional, Union, IO
from helpers.datastructs import SRL

from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
import os


class Repository:
    def __init__(self):
        self._map = {}

    def _read_from_zip_chain(self, parts: list[str]) -> bytes:
        """
        Recursively reads a file through a chain of ZIPs.
        Example: path/to/a.zip|inner.zip|file.png
        """
        current_bytes = None

        for i, part in enumerate(parts):
            if i == 0:
                # First part is always a real file on disk
                with open(part, "rb") as f:
                    current_bytes = f.read()
            else:
                # Open previous bytes as ZIP
                with ZipFile(BytesIO(current_bytes)) as zip_file:
                    try:
                        current_bytes = zip_file.read(zip_file.getinfo(part))
                    except KeyError:
                        raise FileNotFoundError(f"{part} not found in zip chain")
        return current_bytes

    def add_file(
        self, file: os.PathLike, error_on_file_nonexistent: bool = True
    ) -> Optional[str]:
        if not error_on_file_nonexistent:
            if not os.path.exists(file):
                return None
        hash = self.get_hash_from_file_path(file)
        if hash:
            del self._map[hash]
        if "|" in str(file):
            file_data = self._read_from_zip_chain(str(file).split("|"))
            sha1 = calculate_sha1(file_data)
        else:
            sha1 = calculate_sha1(file)
        file_path = str(file)
        if sha1 not in self._map.keys():
            self._map[sha1] = {"hash": sha1, "file": file_path}
        return sha1

    def add_bytes(self, data: Union[IO[bytes], bytes]):
        """
        Warning: cannot be updated!
        """
        sha1 = calculate_sha1(data)
        if sha1 not in self._map.keys():
            self._map[sha1] = {"hash": sha1, "file": data}

    def pop_hash(self, hash: str) -> Optional[bytes]:
        file_data = self.get_file(hash)
        if file_data:
            del self._map[hash]
        return file_data

    def update_file(self, file: os.PathLike):
        """
        Alias for add_file lol
        """
        self.add_file(file)

    def get_hash_from_file_path(self, file: os.PathLike) -> Optional[str]:
        input_path = os.path.abspath(file)
        for sha1, data in self._map.items():
            if type(data["file"]) != str:
                continue
            stored_path = os.path.abspath(data["file"])
            if input_path == stored_path:
                return sha1
        return None

    def get_file(self, hash: str) -> Optional[bytes]:
        item = self._map.get(hash, None)
        if not item:
            return None
        file = item["file"]
        file_data: Optional[bytes] = None
        if isinstance(file, (str, Path)):
            file_path = Path(file)
            if "|" in str(file_path):
                # Handle files in ZIP (this is chainable)
                parts = str(file_path).split("|")
                file_data = self._read_from_zip_chain(parts)
            else:
                with open(file_path, "rb") as f:
                    file_data = f.read()
        elif isinstance(file, BytesIO):
            file.seek(0)
            file_data = file.read()
        elif isinstance(file, bytes):
            file_data = file
        return file_data

    def get_srl(self, hash: str) -> Optional[SRL]:
        if hash in self._map.keys():
            return {"hash": hash, "url": f"/sonolus/repository/{hash}"}
        return None


repo = Repository()
