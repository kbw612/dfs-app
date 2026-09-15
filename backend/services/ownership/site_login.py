"""
Shared login flow for oneweekseason.com -- used by every scraper on this
site that needs an authenticated session. Originally lived in scraper.py
(the /basic-ownership-dk scrape, which has always required login), moved
here once main_slate_scraper.py (the DraftKings Main Slate page) also
started needing it -- that page is free early in the week but the site
switches it to login-required later on, so that scraper has to be able to
authenticate too, on the exact same login form.

Login flow: GET the login page, harvest every existing form field
(WordPress logins often carry a nonce or similar the site expects back
unchanged), override just the username/password fields, then POST to
whatever the form's own `action` resolves to -- this replicates what the
ported notebook's mechanize select_form()+submit() did without hardcoding
assumptions about which hidden fields exist today. `rcp_user_login`/
`rcp_user_pass` are Restrict Content Pro's (the membership plugin this
site runs) own field names for its login form.
"""

from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from backend.config import settings

_LOGIN_PATH = "/login/"


def login(session: requests.Session, base_url: str, username: str, password: str) -> None:
    """Authenticates `session` in place against oneweekseason.com's login
    form. Raises requests.HTTPError on a network-level failure; does NOT
    itself verify the login succeeded -- bad credentials just leave the
    session unauthenticated, which each caller's own parsing surfaces as a
    Message once the expected table isn't found."""
    login_url = urljoin(base_url, _LOGIN_PATH)
    response = session.get(login_url, timeout=settings.request_timeout_seconds)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    form = soup.find("form")
    if form is None:
        raise RuntimeError(f"No <form> found on login page: {login_url}")

    form_data: dict[str, str] = {}
    for field in form.find_all(["input", "textarea"]):
        name = field.get("name")
        if name:
            form_data[name] = field.get("value", "")

    form_data["rcp_user_login"] = username
    form_data["rcp_user_pass"] = password

    submit_url = urljoin(login_url, form.get("action") or login_url)
    method = (form.get("method") or "post").strip().lower()
    submit = session.post if method == "post" else session.get

    response = submit(submit_url, data=form_data, timeout=settings.request_timeout_seconds)
    response.raise_for_status()
