import re
import requests
from bs4 import BeautifulSoup
from django.utils import timezone
from django.utils.text import slugify
from datetime import timedelta, datetime

from quizmaker.models import NewsArticle
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def fetch_pib_feed():
    """
    Fetches PIB's official press-release RSS feed and returns a list of
    (title, link, prid) tuples. The feed itself only ever provides title
    and link - no dates, no guid, no body text - confirmed via direct
    inspection.
    """
    url = "https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=1&reg=1"
    response = requests.get(url, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "xml")
    items = []
    for item in soup.find_all("item"):
        title = item.find("title").text.strip()
        link = item.find("link").text.strip()
        prid_match = re.search(r"PRID=(\d+)", link)
        if not prid_match:
            continue
        items.append((title, link, prid_match.group(1)))

    return items


def parse_pib_article(url):
    response = requests.get(url, timeout=15)
    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.content, "html.parser")
    for tag in soup.find_all(["img", "script", "style"]):
        tag.decompose()

    page_text = soup.get_text(separator="\n")

    published_at = None
    for marker in ["Posted On:", "प्रविष्टि तिथि:"]:
        idx = page_text.find(marker)
        if idx != -1:
            date_segment = page_text[idx + len(marker):idx + len(marker) + 40]
            match = re.search(r"(\d{1,2} [A-Z]{3} \d{4} \d{1,2}:\d{2}[AP]M)", date_segment)
            if match:
                published_at = match.group(1)
            break

    issuing_authority, title = extract_title_and_authority(page_text)
    cleaned_text = clean_whitespace(page_text)
    cleaned_text = strip_duplicate_block(cleaned_text, issuing_authority, title)

    return {
        "issuing_authority": issuing_authority,
        "title": title,
        "published_at_raw": published_at,
        "raw_text": cleaned_text,
    }


def clean_whitespace(text):
    # Collapse 3+ consecutive blank lines down to a single blank line,
    # and strip trailing whitespace from every line
    lines = [line.rstrip() for line in text.split("\n")]
    cleaned = []
    blank_run = 0
    for line in lines:
        if line == "":
            blank_run += 1
            if blank_run > 1:
                continue
        else:
            blank_run = 0
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def extract_title_and_authority(page_text):
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]
    # Skip the generic page-title line ("Press Release:Press Information Bureau")
    content_lines = [l for l in lines if l != "Press Release:Press Information Bureau"]
    issuing_authority = content_lines[0] if content_lines else ""
    title = content_lines[1] if len(content_lines) > 1 else ""
    return issuing_authority, title


def strip_duplicate_block(raw_text, issuing_authority, title):
    if not issuing_authority or not title:
        return raw_text

    pattern = re.escape(issuing_authority) + r"\s*" + re.escape(title)
    matches = list(re.finditer(pattern, raw_text))

    if len(matches) < 2:
        return raw_text  # no duplicate found, nothing to strip

    second_match_start = matches[1].start()
    return raw_text[:second_match_start].strip()


def parse_published_date(raw_string):
    if not raw_string:
        return None
    try:
        naive_dt = datetime.strptime(raw_string, "%d %b %Y %I:%M%p")
        return naive_dt.replace(tzinfo=IST)
    except ValueError:
        return None


def poll_pib_feed():
    """
    Fetches the current PIB feed, and for every genuinely new item,
    fetches the full article and stores it. Returns a count of how
    many new articles were actually saved.
    """
    items = fetch_pib_feed()
    saved_count = 0

    for title, link, prid in items:
        if NewsArticle.objects.filter(pib_release_id=prid).exists():
            continue  # already have this exact release

        new_slug = slugify(title)[:60]
        recent_cutoff = timezone.now() - timedelta(hours=48)
        is_near_duplicate = NewsArticle.objects.filter(
            title_slug=new_slug, created_at__gte=recent_cutoff
        ).exists()
        if is_near_duplicate:
            continue  # same real event, different PRID - skip the redundant fetch entirely

        parsed = parse_pib_article(link)
        if parsed is None:
            continue  # article page couldn't be fetched (e.g. retired PRID)

        published_at = parse_published_date(parsed["published_at_raw"])

        NewsArticle.objects.create(
            pib_release_id=prid,
            title=parsed["title"] or title,
            title_slug=new_slug,
            issuing_authority=parsed["issuing_authority"],
            source_url=link,
            published_at=published_at,
            raw_text=parsed["raw_text"],
        )
        saved_count += 1

    return saved_count