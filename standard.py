import argparse
import json
import logging
import signal
import time
from pathlib import Path

from crawler.core import BisnisCrawler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

running = True


def handle_signal(*_):
    global running
    logger.info("Stopping after current cycle...")
    running = False


def load_existing(path):
    if not Path(path).exists():
        return [], set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            articles = json.load(f)
        return articles, {a["link"] for a in articles if "link" in a}
    except (json.JSONDecodeError, OSError):
        return [], set()


def run_cycle(crawler, output, seen):
    items = crawler.get_sitemap_articles()
    new_urls = [x["url"] for x in items if x["url"] not in seen]
    logger.info("Sitemap: %d entries, %d new", len(items), len(new_urls))

    if not new_urls:
        return

    articles, _ = load_existing(output)
    for i, url in enumerate(new_urls, 1):
        logger.info("[%d/%d] Scraping: %s", i, len(new_urls), url)
        article = crawler.scrape_article(url)
        if article:
            articles.append(article)
            seen.add(url)
        else:
            logger.warning("Failed: %s", url)

    BisnisCrawler.save_json(articles, output)


def main():
    parser = argparse.ArgumentParser(
        description="Standard crawler: long-running process that polls bisnis.com for new articles."
    )
    parser.add_argument("--interval", type=int, default=300,
                        help="Fetch interval in seconds (default: 300)")
    parser.add_argument("--output", default="standard_output.json")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Seconds between requests (default: 1.0)")
    parser.add_argument("--run-once", action="store_true",
                        help="Run one cycle then exit")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logger.info("Standard mode started: interval=%ds, output=%s", args.interval, args.output)

    crawler = BisnisCrawler(delay=args.delay)
    _, seen = load_existing(args.output)

    while running:
        try:
            run_cycle(crawler, args.output, seen)
        except Exception as e:
            logger.error("Cycle error: %s", e, exc_info=True)

        if args.run_once or not running:
            break

        logger.info("Sleeping %ds...", args.interval)
        for _ in range(args.interval):
            if not running:
                break
            time.sleep(1)

    logger.info("Standard crawler stopped.")


if __name__ == "__main__":
    main()
