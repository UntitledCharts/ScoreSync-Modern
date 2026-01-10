import hashlib
from typing import Union, IO
from io import BytesIO
from pathlib import Path
import os


def calculate_sha1(data: Union[os.PathLike, IO[bytes], bytes]) -> str:
    sha1_hash = hashlib.sha1()

    if isinstance(data, (str, Path)):
        with open(data, "rb") as file:
            while chunk := file.read(8192):
                sha1_hash.update(chunk)
    elif isinstance(data, BytesIO):
        while chunk := data.read(8192):
            sha1_hash.update(chunk)
    elif isinstance(data, bytes):
        sha1_hash.update(data)
    else:
        raise ValueError(
            "Input must be a file path (str/Path), BytesIO object, or raw data (bytes)."
        )

    return sha1_hash.hexdigest()
