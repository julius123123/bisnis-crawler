import argparse
import logging
import sys
from datetime import date, datetime

from crawler.core import BisnisCrawler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

INDEX_COVERAGE_DAYS = 4


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date '{value}'. Expected YYYY-MM-DD.")


def collect_from_index(crawler, start, end):
    total = crawler.get_total_index_pages()
    logger.info("Index source: %d pages", total)
    collected, seen = [], set()
    for page in range(1, total + 1):
        logger.info("Scanning index page %d / %d", page, total)
        urls = crawler.get_index_page_urls(page)
        dates = [d for d in (BisnisCrawler.date_from_url(u) for u in urls) if d]
        if not dates:
            continue
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            d = BisnisCrawler.date_from_url(url)
            if d and start <= d <= end:
                collected.append(url)
        if max(dates) < start:
            break
    logger.info("Collected %d URLs from index", len(collected))
    return collected


def collect_from_search(crawler, start, end):
    collected = list(crawler.iter_search_urls(start, end))
    logger.info("Collected %d URLs from search", len(collected))
    return collected


def main():
    parser = argparse.ArgumentParser(
        description="Backtrack crawler: scrape bisnis.com articles within a date range."
    )
    parser.add_argument("--start-date", required=True, type=parse_date, metavar="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, type=parse_date, metavar="YYYY-MM-DD")
    parser.add_argument("--output", default="backtrack_output.json")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Seconds between requests (default: 1.0)")
    parser.add_argument("--source", choices=["auto", "index", "search"], default="auto",
                        help="auto: index for recent dates, search for older ones")
    args = parser.parse_args()

    if args.start_date > args.end_date:
        logger.error("--start-date must be before or equal to --end-date")
        sys.exit(1)

    logger.info("Backtrack: %s to %s (source=%s)", args.start_date, args.end_date, args.source)

    crawler = BisnisCrawler(delay=args.delay)

    use_search = args.source == "search" or (
        args.source == "auto" and (date.today() - args.start_date).days > INDEX_COVERAGE_DAYS
    )

    urls = collect_from_search(crawler, args.start_date, args.end_date) if use_search \
        else collect_from_index(crawler, args.start_date, args.end_date)

    if not urls:
        logger.warning("No articles found in the given date range.")
        BisnisCrawler.save_json([], args.output)
        return

    articles = []
    for i, url in enumerate(urls, 1):
        logger.info("[%d/%d] Scraping: %s", i, len(urls), url)
        article = crawler.scrape_article(url)
        if article:
            articles.append(article)
        else:
            logger.warning("Failed: %s", url)

    BisnisCrawler.save_json(articles, args.output)
    logger.info("Done: %d / %d articles saved to %s", len(articles), len(urls), args.output)


if __name__ == "__main__":
    main()
