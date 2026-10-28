"""Run exactly one backend/worker process; never use uvicorn --reload or --workers."""
import argparse
import logging
import os

import uvicorn
from backend.app import create_app
from backend.config import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=8000, type=int)
    parser.add_argument('--external-engine', action='store_true', help='Do not start/restart an owned ComfyUI child')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    origins = os.getenv('MOSS_ALLOWED_ORIGINS')
    settings = Settings(engine_autostart=not args.external_engine, bootstrap_default_admin=True,
                        secure_cookie=os.getenv('MOSS_SECURE_COOKIE', '0') == '1')
    if origins:
        settings.allowed_origins = tuple(x.strip() for x in origins.split(',') if x.strip())
    uvicorn.run(create_app(settings), host=args.host, port=args.port, workers=1, proxy_headers=False)


if __name__ == '__main__':
    main()
