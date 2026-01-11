from helpers.sonolus_typings import ItemType
from helpers.create_level_item import create_level_item
from helpers.levels import load_levels_directory
from fastapi import APIRouter, Request, HTTPException, status

router = APIRouter()


@router.get("/sonolus/{item_type}/{item_name}")
async def main(request: Request, item_type: ItemType, item_name: str):

    level_data = await request.app.run_blocking(
        load_levels_directory, request.app.bgver
    )
    found_level_data = next(
        ((k, d) for k, d in level_data.items() if d["id"] == item_name), None
    )

    if not found_level_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    data = {
        "item": create_level_item(request, found_level_data[1], found_level_data[0]),
        "actions": [],
        "hasCommunity": False,
        "leaderboards": [],
        "sections": [],
    }
    return data
