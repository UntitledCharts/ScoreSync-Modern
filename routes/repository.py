from fastapi import APIRouter, Request, status, Response
from fastapi import HTTPException

from helpers.repository import repo

router = APIRouter()


@router.get("/sonolus/repository/{hash}")
async def main(request: Request, hash: str):
    file_data = await request.app.run_blocking(repo.get_file, hash)
    if file_data:
        return Response(content=file_data)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
