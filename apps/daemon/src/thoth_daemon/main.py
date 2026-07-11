import uvicorn

from thoth_daemon.app import create_app
from thoth_daemon.config import Settings


def run() -> None:
    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    run()
