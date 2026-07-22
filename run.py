"""网页后台启动入口。"""

from __future__ import annotations

import uvicorn

from app.config import settings


def main() -> None:
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
