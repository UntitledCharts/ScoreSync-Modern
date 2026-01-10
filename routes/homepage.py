from helpers.repository import repo
from fastapi import APIRouter, Request, HTTPException, status

router = APIRouter()


@router.get("/sonolus/info")
async def main(request: Request):
    desc = "ScoreSync Modern - https://github.com/UntitledCharts/ScoreSync-Modern"

    data = {
        "title": "ScoreSync Modern",
        "description": desc,
        "buttons": [{"type": "level"}],
        "configuration": {"options": []},
    }
    data["banner"] = repo.get_srl(request.app.files["banner"])
    return data
