import os
import sys
import json
import re
import subprocess
import logging
import time
import yaml
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

# Project root
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
LOGS_DIR = BASE_DIR / "logs"
TEMPLATE_DIR = BASE_DIR / "templates"


def setup_logging(date_str):
    """Setup logging to logs/YYYY-MM-DD.log"""
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"{date_str}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )


def load_config():
    """Load config.yaml"""
    with open(BASE_DIR / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def already_generated_today(date_str):
    """Check if today's report already exists"""
    return (OUTPUT_DIR / f"{date_str}.html").exists()


def collect_category(category_key, category_config, topics_count, timeout):
    """Collect info for one category via claude CLI with WebSearch"""
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""今日は{today}です。{category_config['query']}について最新の情報を{topics_count}件調査してください。
日本語・英語両方のソースから収集し、日本語でまとめてください。

以下のフォーマットで出力してください（各トピックを---で区切る）:

### タイトル
サマリー（100-200文字程度）
Source: URL

---

### タイトル
サマリー
Source: URL
"""
    logging.info(f"Collecting {category_key}...")

    result = subprocess.run(
        ['claude', '-p', prompt, '--allowedTools', 'WebSearch', '--output-format', 'json'],
        capture_output=True, text=True, timeout=timeout, cwd=str(BASE_DIR)
    )

    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {result.stderr}")

    output = json.loads(result.stdout)
    return output.get("result", "")


def parse_topics(markdown_text):
    """Parse markdown output from claude into structured topic list"""
    topics = []

    # Split by ### headers
    sections = re.split(r'(?=^### )', markdown_text, flags=re.MULTILINE)

    for section in sections:
        section = section.strip()
        if not section.startswith("###"):
            continue

        lines = section.split("\n")
        title = lines[0].replace("### ", "").strip()

        # Extract source URL
        source = ""
        summary_lines = []
        for line in lines[1:]:
            line = line.strip()
            if not line or line == "---":
                continue
            # Look for source URL patterns
            source_match = re.match(r'(?:Source|ソース|出典)[:：]\s*(https?://\S+)', line)
            if source_match:
                source = source_match.group(1)
            # Also check for markdown link format: [text](url)
            elif re.match(r'-?\s*\[.*?\]\(https?://.*?\)', line):
                url_match = re.search(r'\((https?://[^\)]+)\)', line)
                if url_match:
                    source = url_match.group(1)
            else:
                summary_lines.append(line)

        summary = " ".join(summary_lines).strip()
        if title:
            topics.append({
                "title": title,
                "summary": summary,
                "source": source
            })

    return topics


def collect_all(config):
    """Collect info for all categories"""
    categories_result = {}

    for key, cat_config in config["categories"].items():
        try:
            raw_result = collect_category(
                key, cat_config,
                config["topics_per_category"],
                config["claude_timeout_sec"]
            )
            topics = parse_topics(raw_result)

            if not topics:
                # Fallback: use raw result as single topic
                logging.warning(f"Parse failed for {key}, using raw fallback")
                topics = [{"title": cat_config["name"], "summary": raw_result[:500], "source": ""}]

            categories_result[key] = {
                "name": cat_config["name"],
                "topics": topics
            }
            logging.info(f"Collected {len(topics)} topics for {key}")
        except Exception as e:
            logging.error(f"Failed to collect {key}: {e}")
            raise

    return categories_result


def generate_report_html(date_str, generated_at, categories):
    """Generate daily report HTML from template"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("report.html")
    html = template.render(
        date=date_str,
        generated_at=generated_at,
        categories=categories
    )
    output_path = OUTPUT_DIR / f"{date_str}.html"
    output_path.write_text(html, encoding="utf-8")
    logging.info(f"Generated report: {output_path}")
    return output_path


def generate_index_html():
    """Regenerate index.html with list of all reports"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("index.html")

    # Find all report HTML files (YYYY-MM-DD.html pattern)
    report_files = sorted(
        [f.stem for f in OUTPUT_DIR.glob("????-??-??.html")],
        reverse=True
    )[:30]  # Last 30 days

    reports = [{"date": date} for date in report_files]
    latest_date = report_files[0] if report_files else None

    html = template.render(latest_date=latest_date, reports=reports)
    index_path = OUTPUT_DIR / "index.html"
    index_path.write_text(html, encoding="utf-8")
    logging.info(f"Generated index: {index_path}")


def git_push(date_str):
    """Commit and push generated HTML to GitHub"""
    try:
        subprocess.run(['git', 'add', 'output/'], check=True, cwd=str(BASE_DIR))
        subprocess.run(
            ['git', 'commit', '-m', f'Add daily report {date_str}'],
            check=True, cwd=str(BASE_DIR)
        )
        subprocess.run(['git', 'push', 'origin', 'main'], check=True, cwd=str(BASE_DIR))
        logging.info(f"Pushed report {date_str} to GitHub")
    except subprocess.CalledProcessError as e:
        logging.error(f"Git operation failed: {e}")
        raise


def notify_teams(date_str, topics_count, config):
    """Send notification to Teams via Incoming Webhook"""
    webhook_url = os.environ.get("TEAMS_WEBHOOK_URL", "")
    if not webhook_url:
        logging.warning("TEAMS_WEBHOOK_URL not set, skipping notification")
        return

    base_url = config.get("github_pages_base_url", "")
    report_url = f"{base_url}/{date_str}.html" if base_url else ""

    card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {
                        "type": "TextBlock",
                        "text": f"AI Daily Report - {date_str}",
                        "weight": "Bolder",
                        "size": "Medium"
                    },
                    {
                        "type": "TextBlock",
                        "text": f"{topics_count}件のトピックを収集しました",
                        "wrap": True
                    }
                ]
            }
        }]
    }

    # Add link action if base URL is configured
    if report_url:
        card["attachments"][0]["content"]["actions"] = [{
            "type": "Action.OpenUrl",
            "title": "レポートを見る",
            "url": report_url
        }]

    try:
        resp = requests.post(webhook_url, json=card, timeout=30)
        resp.raise_for_status()
        logging.info("Teams notification sent")
    except Exception as e:
        logging.error(f"Teams notification failed: {e}")
        # Don't raise - notification failure shouldn't block the pipeline


def run_with_retry(config):
    """Run the main pipeline with retry logic"""
    today = datetime.now().strftime("%Y-%m-%d")
    max_retries = config.get("retry_max", 3)
    interval = config.get("retry_interval_sec", 1800)

    for attempt in range(1, max_retries + 1):
        try:
            logging.info(f"Attempt {attempt}/{max_retries}")

            # Collect
            categories = collect_all(config)
            total_topics = sum(len(c['topics']) for c in categories.values())

            # Generate HTML
            generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            generate_report_html(today, generated_at, categories)
            generate_index_html()
            logging.info("HTML generation complete")

            # Git push
            git_push(today)

            # Notify Teams
            notify_teams(today, total_topics, config)

            logging.info(f"Pipeline complete: {total_topics} topics collected and published")
            return  # Success

        except Exception as e:
            logging.error(f"Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                logging.info(f"Retrying in {interval} seconds...")
                time.sleep(interval)
            else:
                logging.error(f"All {max_retries} attempts failed")
                raise


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    setup_logging(today)
    load_dotenv(BASE_DIR / ".env")
    config = load_config()

    # Parse CLI args
    test_collect = "--test-collect" in sys.argv
    test_html = "--test-html" in sys.argv

    if not test_collect and not test_html:
        # Normal mode: check for duplicate
        if already_generated_today(today):
            logging.info(f"Report for {today} already exists. Skipping.")
            return

    if test_collect:
        # Test mode: collect only first category
        first_key = list(config["categories"].keys())[0]
        first_config = config["categories"][first_key]
        raw = collect_category(first_key, first_config, config["topics_per_category"], config["claude_timeout_sec"])
        topics = parse_topics(raw)
        print(f"\n=== Test Collection: {first_key} ===")
        print(f"Raw length: {len(raw)} chars")
        print(f"Parsed topics: {len(topics)}")
        for t in topics:
            print(f"  - {t['title']}")
            print(f"    {t['summary'][:100]}...")
            print(f"    Source: {t['source']}")
        return

    if test_html:
        # Test HTML mode: collect and generate, but skip git push / notify
        logging.info(f"Starting collection for {today}")
        categories = collect_all(config)
        logging.info(f"Collection complete: {sum(len(c['topics']) for c in categories.values())} total topics")
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        generate_report_html(today, generated_at, categories)
        generate_index_html()
        logging.info("HTML generation complete")
        output_path = OUTPUT_DIR / f"{today}.html"
        print(f"Report generated: {output_path}")
        return

    # Normal mode
    run_with_retry(config)


if __name__ == "__main__":
    main()
