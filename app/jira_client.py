import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
from app.cache import get_cache, set_cache, get_cache_meta

load_dotenv()

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

def get_current_user():
    data = jira_get("/myself")

    return {
        "display_name": data.get("displayName"),
        "email": data.get("emailAddress"),
        "account_id": data.get("accountId"),
    }


def jira_get(path, params=None):
    base_url = JIRA_BASE_URL.rstrip("/")
    path = path.lstrip("/")
    url = f"{base_url}/rest/api/3/{path}"

    response = requests.get(
        url,
        params=params,
        auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
        headers={"Accept": "application/json"},
        timeout=30,
    )

    if not response.ok:
        print("Jira error:", response.status_code)
        print(response.text)

    response.raise_for_status()
    return response.json()


def search_issues(jql, max_results=100):
    data = jira_get(
        "/search/jql",
        params={
            "jql": jql,
            "maxResults": max_results,
            "fields": "summary,status,assignee,reporter,priority,updated,project",
        },
    )
    return data.get("issues", [])


def get_issue_comments(issue_key):
    data = jira_get(f"/issue/{issue_key}/comment", params={"orderBy": "created"})
    return data.get("comments", [])


def latest_comment_is_from_reporter(issue):
    reporter = issue["fields"].get("reporter")

    if not reporter:
        return False, None

    reporter_account_id = reporter.get("accountId")
    comments = get_issue_comments(issue["key"])

    if not comments:
        return False, None

    latest_comment = comments[-1]
    latest_author = latest_comment.get("author", {})

    return latest_author.get("accountId") == reporter_account_id, latest_comment


def latest_comment_mentions_reporter(issue):
    reporter = issue["fields"].get("reporter")

    if not reporter:
        return False, None

    reporter_account_id = reporter.get("accountId")
    comments = get_issue_comments(issue["key"])

    if not comments:
        return False, None

    latest_comment = comments[-1]
    body = str(latest_comment.get("body", ""))

    mentioned = reporter_account_id in body

    return mentioned, latest_comment


def format_issue(issue, latest_comment=None):
    fields = issue["fields"]
    priority = fields.get("priority", {}).get("name") if fields.get("priority") else "None"

    priority_rank = {
        "Highest": 1,
        "High": 2,
        "Medium": 3,
        "Low": 4,
        "Lowest": 5,
        "None": 99,
    }

    return {
        "key": issue["key"],
        "summary": fields.get("summary"),
        "project": fields.get("project", {}).get("key"),
        "status": fields.get("status", {}).get("name"),
        "priority": priority,
        "priority_sort": priority_rank.get(priority, 99),
        "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else "Unassigned",
        "reporter": fields.get("reporter", {}).get("displayName") if fields.get("reporter") else "",
        "updated": fields.get("updated"),
        "latest_comment_created": latest_comment.get("created") if latest_comment else "",
        "action_date": latest_comment.get("created") if latest_comment else fields.get("updated"),
        "url": f"{JIRA_BASE_URL}/browse/{issue['key']}",
    }


def get_actionable_items():
    results = []

    # -------- TS --------
    ts_jql = """
        project = TS
        AND assignee = currentUser()
        AND statusCategory != Done
        ORDER BY updated DESC
    """

    ts_issues = search_issues(ts_jql)

    for issue in ts_issues:
        actionable, latest_comment = latest_comment_is_from_reporter(issue)

        if actionable:
            ticket = format_issue(issue, latest_comment)
            ticket["project"] = "TS"
            results.append(ticket)

    # -------- CP --------
    cp_jql = """
        project = CP
        AND assignee = currentUser()
        AND statusCategory != Done
        ORDER BY updated DESC
    """

    cp_issues = search_issues(cp_jql)

    for issue in cp_issues:
        actionable, latest_comment = latest_comment_mentions_reporter(issue)

        if actionable:
            ticket = format_issue(issue, latest_comment)
            ticket["project"] = "CP"
            results.append(ticket)

    results.sort(key=lambda x: (
        x["priority_sort"],
        x["action_date"] or x["updated"]
        ))

    return results


def get_waiting_for_product_tickets():
    jql = """
        project = TS
        AND assignee = currentUser()
        AND statusCategory != Done
        AND status = "Waiting for Product"
        ORDER BY updated DESC
    """

    return [format_issue(issue) for issue in search_issues(jql)]


def get_waiting_for_client_tickets():
    jql = """
        project = TS
        AND assignee = currentUser()
        AND statusCategory != Done
        AND status = "Waiting for Client"
        ORDER BY updated DESC
    """

    return [format_issue(issue) for issue in search_issues(jql)]


def get_waiting_for_operations_tickets():
    jql = """
        project = TS
        AND assignee = currentUser()
        AND statusCategory != Done
        AND status = "Waiting for Operations"
        ORDER BY updated DESC
    """

    return [format_issue(issue) for issue in search_issues(jql)]


def get_cp_reporter_tagged_tickets():
    jql = """
        project = CP
        AND assignee = currentUser()
        AND statusCategory != Done
        ORDER BY updated DESC
    """

    issues = search_issues(jql)
    results = []

    for issue in issues:
        mentioned, latest_comment = latest_comment_mentions_reporter(issue)
        if mentioned:
            results.append(format_issue(issue, latest_comment))

    return results


CATEGORIES = {
    "actionable": {
        "title": "Actionable Items",
        "description": "Tickets requiring your attention.",
        "loader": get_actionable_items,
    },
    "waiting-product": {
        "title": "Waiting for Product",
        "description": "TS tickets currently waiting for Product.",
        "loader": get_waiting_for_product_tickets,
    },
    "waiting-client": {
        "title": "Waiting for Client",
        "description": "TS tickets currently waiting for Client.",
        "loader": get_waiting_for_client_tickets,
    },
    "waiting-operations": {
        "title": "Waiting for Operations",
        "description": "TS tickets currently waiting for Operations.",
        "loader": get_waiting_for_operations_tickets,
    },
}


def get_dashboard_tiles():
    tiles = []

    for key, category in CATEGORIES.items():
        _, issues = get_category_issues(key)

        tiles.append({
            "key": key,
            "title": category["title"],
            "description": category["description"],
            "count": len(issues),
        })

    return tiles


def get_category_issues(category_key):
    category = CATEGORIES.get(category_key)

    if not category:
        return None, []

    cache_key = f"category:{category_key}"
    cached = get_cache(cache_key)

    if cached is not None:
        return category, cached["value"]

    issues = category["loader"]()

    set_cache(cache_key, issues)
    return category, issues

def get_category_cache_meta(category_key):
    meta = get_cache_meta(f"category:{category_key}")

    if not meta:
        return {
            "last_sync": "Not synced yet",
            "next_sync": "",
            "next_sync_iso": "",
        }

    return {
        "last_sync": meta["created_at"].strftime("%b %d, %Y %I:%M %p"),
        "next_sync": meta["expires_at"].strftime("%b %d, %Y %I:%M %p"),
        "next_sync_iso": meta["expires_at"].isoformat(),
    }