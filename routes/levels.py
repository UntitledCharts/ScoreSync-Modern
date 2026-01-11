from helpers.sonolus_typings import ItemType
from helpers.repository import repo
from fastapi import APIRouter, Request, HTTPException, status

from helpers.create_level_item import create_level_item
from helpers.levels import load_levels_directory

router = APIRouter()


@router.get("/sonolus/{item_type}/info")
async def main(request: Request, item_type: ItemType):
    levels = await request.app.run_blocking(load_levels_directory, request.app.bgver)
    items = list(levels.items())
    page_items = items[:20]

    converted_data = [create_level_item(request, i[1], i[0]) for i in page_items]
    for item in converted_data:
        if item["cover"] == None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"\n\n.png/.jpg/.jpeg???\n/levels/{item['title']}",
            )
        if item["bgm"] == None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"\n\n.mp3/.ogg???\n/levels/{item['title']}",
            )
        if item["data"] == None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"\n\n.sus/.usc/LevelData/.json/.gz/.mmws/.ccmmws/.unchmmws???\n/levels/{item['title']}",
            )
    data = {
        "sections": [{"title": "#LEVEL", "itemType": "level", "items": converted_data}]
    }
    data["banner"] = repo.get_srl(request.app.files["banner"])
    return data


@router.get("/sonolus/{item_type}/list")
async def main(request: Request, item_type: ItemType):
    ITEMS_PER_PAGE = 10
    page = int(request.query_params.get("page", 0))  # 0-based page

    levels = await request.app.run_blocking(load_levels_directory, request.app.bgver)
    items = list(levels.items())

    total_items = len(items)
    page_count = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    page_items = items[start:end]

    converted_data = [create_level_item(request, i[1], i[0]) for i in page_items]
    for item in converted_data:
        if item["cover"] == None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"\n\n.png/.jpg/.jpeg???\n/levels/{item['title']}",
            )
        if item["bgm"] == None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"\n\n.mp3/.ogg???\n/levels/{item['title']}",
            )
        if item["data"] == None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"\n\n.sus/.usc/LevelData/.json/.gz/.mmws/.ccmmws/.unchmmws???\n/levels/{item['title']}",
            )
    data = {"pageCount": page_count, "items": converted_data}
    return data
