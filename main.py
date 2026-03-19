import logging
import argparse
from sync import sync_once, run_forever
from config import POLL_INTERVAL, ASANA_PAT, NOTION_TOKEN, ASANA_PROJECT_GIDS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def validate_config() -> bool:
    ok = True
    if not ASANA_PAT:
        logging.error("ASANA_PAT が設定されていません（.env を確認）")
        ok = False
    if not NOTION_TOKEN:
        logging.error("NOTION_TOKEN が設定されていません（.env を確認）")
        ok = False
    if not ASANA_PROJECT_GIDS:
        logging.error("ASANA_PROJECT_GIDS が設定されていません（.env を確認）")
        ok = False
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Asana → Notion 同期ツール")
    parser.add_argument(
        "--once",
        action="store_true",
        help="1回だけ同期して終了する（デフォルトは無限ループ）",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=POLL_INTERVAL,
        help=f"ポーリング間隔（秒）デフォルト: {POLL_INTERVAL}",
    )
    args = parser.parse_args()

    if not validate_config():
        raise SystemExit(1)

    logging.info(f"Projects: {ASANA_PROJECT_GIDS}")
    logging.info(f"Interval: {args.interval}s")

    if args.once:
        sync_once()
    else:
        run_forever(args.interval)


if __name__ == "__main__":
    main()
