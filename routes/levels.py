from helpers.sonolus_typings import ItemType
from helpers.repository import repo
from fastapi import APIRouter, Request, HTTPException, status

from helpers.create_level_item import create_level_item
from helpers.levels import load_levels_directory

router = APIRouter()


@router.get("/sonolus/{item_type}/info")
async def main(request: Request, item_type: ItemType):
    levels = await request.app.run_blocking(load_levels_directory, request.app.bgver)
    items = list(levels.values())
    page_items = items[:20]

    converted_data = [
        create_level_item(request, i, i["normalized"]) for i in page_items
    ]
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
    items = list(levels.values())

    total_items = len(items)
    page_count = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    page_items = items[start:end]

    converted_data = [
        create_level_item(request, i, i["normalized"]) for i in page_items
    ]

    data = {"pageCount": page_count, "items": converted_data}
    return data
