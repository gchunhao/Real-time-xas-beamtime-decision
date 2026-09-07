from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local XAS decision-support application")
    parser.add_argument("--config", default="config/app.yaml")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    arguments = parser.parse_args()
    os.environ["XAS_CONFIG"] = arguments.config
    from .config import load_config
    config = load_config(arguments.config)
    import uvicorn
    uvicorn.run(
        "xas_beamtime.api:app",
        host=arguments.host or config.get("server.host", "127.0.0.1"),
        port=arguments.port or int(config.get("server.port", 8765)),
        reload=False,
    )


if __name__ == "__main__":
    main()
