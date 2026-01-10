def main():
    import asyncio
    from app import start_fastapi

    asyncio.run(start_fastapi())


if __name__ == "__main__":
    main()
