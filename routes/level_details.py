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

    item = create_level_item(request, found_level_data[1], found_level_data[0])

    if item["cover"] == None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"\n\n.png/.jpg/.jpeg???\n/levels/{found_level_data[0]}",
        )
    if item["bgm"] == None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"\n\n.mp3/.ogg???\n/levels/{found_level_data[0]}",
        )
    if item["data"] == None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"\n\n.sus/.usc/LevelData/.json/.gz/.mmws/.ccmmws/.unchmmws???\n/levels/{found_level_data[0]}",
        )

    data = {
        "item": item,
        "actions": [],
        "hasCommunity": False,
        "leaderboards": [],
        "sections": [],
    }
    return data
