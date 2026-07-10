#!/usr/bin/env python3
"""Refresh the terminal-style stats block in README.md with live GitHub data.

Runs in CI (see .github/workflows/update-readme.yml) on a schedule. Uses the
GitHub GraphQL API to pull public repo/star/follower/commit counts and
rewrites the text between the STATS:START / STATS:END markers in README.md.
Static fields (Role, Experience, Stack, ...) are left untouched.
"""

import datetime
import json
import os
import re
import sys
import urllib.request

README_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md")
GRAPHQL_URL = "https://api.github.com/graphql"

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!, $after: String) {
  user(login: $login) {
    followers { totalCount }
    repositories(first: 100, after: $after, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes { stargazerCount }
    }
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
    }
  }
}
"""


def graphql(token, variables):
    body = json.dumps({"query": QUERY, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "hlebkanonik-readme-bot",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if "errors" in payload:
        raise RuntimeError(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def fetch_stats(token, login):
    now = datetime.datetime.now(datetime.timezone.utc)
    one_year_ago = now - datetime.timedelta(days=365)
    from_iso = one_year_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
    to_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    followers = 0
    total_repos = 0
    total_stars = 0
    total_commits = 0
    after = None

    while True:
        data = graphql(token, {"login": login, "from": from_iso, "to": to_iso, "after": after})
        followers = data["followers"]["totalCount"]
        total_commits = data["contributionsCollection"]["totalCommitContributions"]
        repos = data["repositories"]
        total_repos = repos["totalCount"]
        total_stars += sum(node["stargazerCount"] for node in repos["nodes"])

        if repos["pageInfo"]["hasNextPage"]:
            after = repos["pageInfo"]["endCursor"]
        else:
            break

    return {
        "followers": followers,
        "repos": total_repos,
        "stars": total_stars,
        "commits": total_commits,
    }


def render_block(stats):
    updated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    return f"""```text
hlebkanonik@devops ~
──────────────────────────────────────────────────
Role:                 Senior DevOps Engineer
Experience:           8 years
Stack:                AWS, GCP, Docker, Kubernetes, Terraform, Ansible
CI/CD:                GitLab CI, GitHub Actions, Jenkins
GitOps:               Declarative configs, Git as source of truth, K8s reconciliation
Working with:         Claude Code, MCP, agentic workflows
──────────────────────────────────────────────────
Public repos:  {stats['repos']:<8} Followers:            {stats['followers']}
Total stars:   {stats['stars']:<8} Commits (last year):  {stats['commits']}
──────────────────────────────────────────────────
Updated: {updated} (auto-generated)
```"""


def main():
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    login = os.environ.get("GH_USERNAME", "hlebkanonik")
    if not token:
        print("GH_TOKEN/GITHUB_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    stats = fetch_stats(token, login)
    new_block = render_block(stats)

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(r"(<!-- STATS:START -->\n).*?(\n<!-- STATS:END -->)", re.DOTALL)
    if not pattern.search(content):
        print("STATS markers not found in README.md", file=sys.stderr)
        sys.exit(1)

    updated_content = pattern.sub(lambda m: m.group(1) + new_block + m.group(2), content)

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(updated_content)

    print("README stats block updated:", stats)


if __name__ == "__main__":
    main()
