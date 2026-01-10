import asyncio, traceback
from contextlib import asynccontextmanager

import psutil
import socket
from typing import List

from pathlib import Path

from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Request
from fastapi import status, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

from helpers.levels import load_levels_directory

# CONSTANTS
PORT = 3939
DEBUG = False
SONOLUS_VERSION = "1.0.2"
BACKGROUND_VERSION = "v3"  # v3, v1

RELATIVE_PATH = Path(__file__).parent


def get_local_ipv4() -> List[str]:
    addresses = []

    for iface_addrs in psutil.net_if_addrs().values():
        for addr in iface_addrs:
            if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                addresses.append(addr.address)

    return addresses if addresses else ["localhost"]


class SonolusFastAPI(FastAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.debug = kwargs["debug"]

        self.executor = ThreadPoolExecutor(max_workers=16)

        self.files = {}
        self.bgver = BACKGROUND_VERSION

        self.exception_handlers.setdefault(HTTPException, self.http_exception_handler)

    async def run_blocking(self, func, *args, **kwargs):
        return await asyncio.get_event_loop().run_in_executor(
            self.executor, lambda: func(*args, **kwargs)
        )

    async def http_exception_handler(self, request: Request, exc: HTTPException):
        if exc.status_code < 500:
            return JSONResponse(
                content={"message": exc.detail}, status_code=exc.status_code
            )
        else:
            print(
                "-" * 1000
                + f"\nerror 500: {request.method} {str(request.url)}\n"
                + "-" * 1000
            )
            return JSONResponse(content={}, status_code=exc.status_code)


class SonolusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Sonolus-Version"] = SONOLUS_VERSION
        return response


app = SonolusFastAPI(debug=DEBUG)


@app.middleware("http")
async def no_unhandled_exceptions(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unhandled error. Report to discord.gg/UntitledCharts",
        )


app.add_middleware(SonolusMiddleware)


async def startup_event():
    import routes

    for router in routes.routers:
        app.include_router(router)

    import helpers.repository

    app.files["banner"] = helpers.repository.repo.add_file(
        RELATIVE_PATH / "assets/banner.png"
    )
    app.files["thumbnail"] = helpers.repository.repo.add_file(
        RELATIVE_PATH / "assets/thumbnail.png"
    )
    app.files["bg_config"] = helpers.repository.repo.add_file(
        RELATIVE_PATH / "assets/background/configuration"
    )
    app.files["bg_data"] = helpers.repository.repo.add_file("assets/background/data")
    app.files["engine_watch"] = helpers.repository.repo.add_file(
        RELATIVE_PATH / "assets/engine/EngineWatchData"
    )
    app.files["engine_play"] = helpers.repository.repo.add_file(
        RELATIVE_PATH / "assets/engine/EnginePlayData"
    )
    app.files["engine_preview"] = helpers.repository.repo.add_file(
        RELATIVE_PATH / "assets/engine/EnginePreviewData"
    )
    app.files["engine_rom"] = helpers.repository.repo.add_file(
        RELATIVE_PATH / "assets/engine/EngineRom"
    )
    app.files["engine_tut"] = helpers.repository.repo.add_file(
        RELATIVE_PATH / "assets/engine/EngineTutorialData"
    )
    app.files["engine_config"] = helpers.repository.repo.add_file(
        RELATIVE_PATH / "assets/engine/EngineConfiguration"
    )
    app.files["bg_image"] = helpers.repository.repo.add_file(
        RELATIVE_PATH / "assets/background/image.png"
    )
    app.files["sfx_audio"] = helpers.repository.repo.add_file(
        RELATIVE_PATH / "assets/effect/audio"
    )
    app.files["sfx_data"] = helpers.repository.repo.add_file(
        RELATIVE_PATH / "assets/effect/data"
    )
    app.files["skin_texture"] = helpers.repository.repo.add_file(
        RELATIVE_PATH / "assets/skin/texture"
    )
    app.files["skin_data"] = helpers.repository.repo.add_file(
        RELATIVE_PATH / "assets/skin/data"
    )
    app.files["particle_texture"] = helpers.repository.repo.add_file(
        RELATIVE_PATH / "assets/particle/texture"
    )
    app.files["particle_data"] = helpers.repository.repo.add_file(
        RELATIVE_PATH / "assets/particle/data"
    )

    load_levels_directory(BACKGROUND_VERSION)

    print("OK!")
    ips = get_local_ipv4()
    for ip in ips:
        print(f"Go to server https://open.sonolus.com/{ip}:{PORT}/")


app.add_event_handler("startup", startup_event)
# uvicorn.run("app:app", port=port, host="0.0.0.0")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.levels = {}
    task = asyncio.create_task(background_loader(app))
    yield
    task.cancel()


async def background_loader(app: SonolusFastAPI):
    while True:
        await app.run_blocking(load_levels_directory, BACKGROUND_VERSION)
        await asyncio.sleep(3)


async def start_fastapi():
    config_server = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=PORT,
        workers=1,
        access_log=DEBUG,
        log_level="critical" if not DEBUG else None,
    )
    server = uvicorn.Server(config_server)
    await server.serve()


if __name__ == "__main__":
    raise SystemExit("Please run main.py")
