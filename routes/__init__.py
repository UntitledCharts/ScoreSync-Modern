from . import homepage, levels, level_details, repository

routers = [
    repository.router,
    homepage.router,
    levels.router,
    level_details.router,
]  # keep levels.router second last and level_details last
