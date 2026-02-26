import asyncio
import random
import re
import json
import logging
from pathlib import Path
from datetime import datetime, timezone, date

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, field_validator, ValidationError

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from db_log_handler import CassandraHandler
from sqlalchemy import create_engine, text


DB_NAME = "crawler_db"
DB_USER = "postgres"
DB_PASS = 12345
DB_HOST = "localhost"
DB_PORT = 5432


def create_database_if_not_exists():
    # Connect to default postgres DB
    default_engine = create_engine(
        f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/postgres",
        isolation_level="AUTOCOMMIT",
    )

    with default_engine.connect() as conn:
        result = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname=:name"),
            {"name": DB_NAME},
        ).fetchone()

        if not result:
            conn.execute(text(f"CREATE DATABASE {DB_NAME}"))
            print(f"Database '{DB_NAME}' created")
        else:
            print(f"Database '{DB_NAME}' already exists")



# Now connect to crawler_db
engine = create_engine(
    f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
    pool_pre_ping=True,
)


def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS articles (
            id SERIAL PRIMARY KEY,
            url TEXT UNIQUE,
            title TEXT,
            content TEXT,
            posted_on DATE,
            scraped_at TIMESTAMP
        );
        """))

def save_article(article):
    with engine.begin() as conn:
        conn.execute(text("""
        INSERT INTO articles (url, title, content, posted_on, scraped_at)
        VALUES (:url, :title, :content, :posted_on, :scraped_at)
        ON CONFLICT (url) DO NOTHING
        """), article)


# Create DB if missing
create_database_if_not_exists()
init_db()
=

Path("logs").mkdir(exist_ok=True)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler("logs/crawler.log")
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(file_handler)

db_handler = CassandraHandler()
db_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(db_handler)



BASE_URL = "https://www.moneycontrol.com/news/business/markets/page-{}/"
OUTPUT_FILE = "articles.jsonl"



class ArticleSchema(BaseModel):
    url: str
    title: str = Field(min_length=5, max_length=500)
    content: str = Field(min_length=50)
    posted_on: date | None
    scraped_at: datetime

    @field_validator("title")
    @classmethod
    def title_not_blocked(cls, v):
        if "access denied" in v.lower():
            raise ValueError("Blocked page detected")
        return v

    @field_validator("content")
    @classmethod
    def content_quality(cls, v):
        if len(v.split()) < 20:
            raise ValueError("Content too small")
        return v



def clean_text(text: str):
    return re.sub(r"\s+", " ", text).strip()


def parse_date(text: str):
    formats = ["%B %d, %Y / %H:%M IST", "%B %d, %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def append_json(article):
    try:
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(article, ensure_ascii=False, default=str) + "\n")

        logger.info(
            "Saved article",
            extra={"article_dic": json.dumps(article)}
        )

    except Exception as e:
        logger.error(f"JSON save failed: {str(e)}")




def parse_article(html, url):
    try:
        soup = BeautifulSoup(html, "lxml")

        title = soup.find("h1").get_text(strip=True) if soup.find("h1") else ""

        body = soup.find("div", class_="content_wrapper") or soup
        content = clean_text("\n".join(
            x.get_text(strip=True) for x in body.find_all(["h2", "p"])
        ))

        posted_on = None
        schedule = soup.find("div", class_="article_schedule")
        if schedule and schedule.find("span"):
            posted_on = parse_date(schedule.find("span").get_text(strip=True))

        article = ArticleSchema(
            url=url,
            title=title,
            content=content,
            posted_on=posted_on,
            scraped_at=datetime.now(timezone.utc),
        )

        return article.model_dump(mode="json")

    except ValidationError as e:
        logger.warning(f"Validation failed: {str(e)}")
        return None

    except Exception as e:
        logger.error(f"Parse error: {str(e)}")
        return None





async def expand_read_more(page):
    try:
        btn = page.locator("text=Read More")

        if await btn.count() == 0:
            return False

        await btn.first.click(timeout=5000)   # reduce timeout
        await page.wait_for_timeout(1500)
        return True

    except PlaywrightTimeoutError:
        # Short log (no huge Playwright call log)
        logger.warning("Read More click intercepted or timed out")
        return False

    except Exception as e:
        # Log short message only
        logger.error(f"Read More error: {e.__class__.__name__}")
        return False




async def scrape_article(page, url):
    try:
        logger.info(f"Scraping article {url}")

        await page.goto(url, timeout=60000, wait_until="domcontentloaded")

        await page.mouse.wheel(0, random.randint(1000, 2000))
        await page.wait_for_timeout(random.randint(2000, 4000))

        await expand_read_more(page)

        html = await page.content()
        article = parse_article(html, url)

        if article:
            append_json(article)
            save_article(article)
            logging.info(f"Saved to DB: {url}")

    except Exception as e:
        logger.error(f"Article failed: {str(e)}")


async def get_links(page, page_no):
    url = BASE_URL.format(page_no)
    logger.info(f"Opening list page {page_no}")

    response = await page.goto(url, timeout=60000, wait_until="domcontentloaded")

    if response is None or response.status != 200:
        logger.warning(f"Failed to load page {page_no}")
        return []

    await page.wait_for_selector("li.clearfix a")

    # await page.wait_for_timeout(random.randint(2000, 4000))
    soup = BeautifulSoup(await page.content(), "lxml")

    links = set()
    for a in soup.select("li.clearfix a"):
        href = a.get("href")
        if isinstance(href, str) and href.endswith(".html"):
            links.add(href)

    logger.info(f"Found {len(links)} links")
    return list(links)




async def crawl():
    logger.info("Crawler started")

    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                locale="en-IN",
                timezone_id="Asia/Kolkata"
            )
            page = await context.new_page()

            page_no = 1
            while True:
                links = await get_links(page, page_no)
                if not links:
                    break

                for link in links:
                    await scrape_article(page, link)

                page_no += 1
                break

    except KeyboardInterrupt:
        logger.warning("Crawler manually stopped")

    except Exception as e:
        logger.critical(f"Crawler crashed: {str(e)}")

    finally:
        if browser:
            await browser.close()

    logger.info("Crawler finished")


def run():
    asyncio.run(crawl())


if __name__ == "__main__":
    run()

    