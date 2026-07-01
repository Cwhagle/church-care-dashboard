"""
============================================================
 CHURCH CARE DASHBOARD
============================================================
A simple Streamlit app that connects Planning Center (PCO)
and Clearstream so the church can see who needs a birthday
note, search for a person, and check the texting inbox --
all from one page on an iPad.

HOW THIS FILE IS ORGANIZED (look for the SECTION headers):
  1. Settings           -- safe things to tweak
  1B. Look & feel       -- colors/fonts (Robinhood-style dark theme)
  1C. Text messages     -- birthday/anniversary message templates
  2. Planning Center    -- talking to the PCO API
  3. Clearstream        -- talking to the Clearstream API
  4. Reusable UI pieces -- the "send a text" box
  5. The actual page    -- all nine tabs

Look for "# >>> TWEAK ME" comments -- those are safe, simple
settings you can change without breaking anything else.
============================================================
"""

import os
import time
import hashlib
import datetime
import requests
import streamlit as st

# ------------------------------------------------------------------
# SECTION 1: SETTINGS
# ------------------------------------------------------------------

# >>> TWEAK ME: how many days ahead counts as an "upcoming" birthday
BIRTHDAY_LOOKAHEAD_DAYS = 7

# >>> TWEAK ME: how many days ahead counts as an "upcoming" anniversary
ANNIVERSARY_LOOKAHEAD_DAYS = 7

# >>> TWEAK ME: how many recent texting conversations to show in the inbox
INBOX_LIMIT = 30

# >>> TWEAK ME: how many days back to look when deciding who's a "regular"
DRIFT_LOOKBACK_DAYS = 60

# >>> TWEAK ME: how many check-ins within that window counts as "regular attendance"
DRIFT_MIN_CHECKINS = 3

# >>> TWEAK ME: if a regular hasn't checked in for this many days, flag them as drifting
DRIFT_THRESHOLD_DAYS = 21

# >>> TWEAK ME: how many days back counts as a "new" profile or first-time guest
NEW_GUEST_LOOKBACK_DAYS = 14

# >>> TWEAK ME: how many "not in a Group" people to show at once (this list
# can be long at a bigger church, so we show a batch at a time instead of
# everyone -- there's a button to see more).
CONNECTION_GAPS_PAGE_SIZE = 25

# The four ministry age groups people get sorted into (see age_category()
# in Section 2 for exactly how). Order matters here -- it's the order
# shown in every "Age group" dropdown.
AGE_CATEGORIES = ["Preschool", "Children", "Youth", "Adults"]

# Secrets come from your host's Secrets manager -- never type real keys
# directly into this file.
PCO_APP_ID = os.environ.get("PCO_APP_ID", "")
PCO_SECRET = os.environ.get("PCO_SECRET", "")
CLEARSTREAM_API_KEY = os.environ.get("CLEARSTREAM_API_KEY", "")
CHURCH_NAME = os.environ.get("CHURCH_NAME", "Our Church")

# >>> TWEAK ME: this isn't a secret, just plain text -- change it any time.
# It's the name that signs off birthday and anniversary text messages below.
PASTOR_NAME = "Pastor Casey Hagle"

PCO_BASE_URL = "https://api.planningcenteronline.com"
CLEARSTREAM_BASE_URL = "https://api.getclearstream.com/v1"

st.set_page_config(page_title="Church Care Dashboard", page_icon="✝️", layout="wide")

# ------------------------------------------------------------------
# SECTION 1B: LOOK & FEEL (Robinhood-style dark theme)
# ------------------------------------------------------------------
# This is plain CSS, injected into the page. It doesn't touch any data
# or logic -- it only changes colors, fonts, and shapes. Safe to tweak
# or delete entirely (just remove this whole st.markdown(...) call)
# without breaking anything else in the app.
#
# >>> TWEAK ME: the hex codes below are the only things you need to
# change to adjust the color scheme. ROBINHOOD_GREEN is used for
# buttons, links, and active tabs. CARD_BG is the color of expander
# "cards" and input boxes.
ROBINHOOD_GREEN = "#00C805"
PAGE_BG = "#000000"
CARD_BG = "#141414"
BORDER = "#2A2A2E"
MUTED_TEXT = "#8E8E93"

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }}

    .stApp {{
        background-color: {PAGE_BG};
        color: #FFFFFF;
    }}

    [data-testid="stHeader"] {{
        background-color: {PAGE_BG};
    }}

    h1 {{
        font-weight: 800;
        letter-spacing: -0.02em;
        color: #FFFFFF;
    }}

    h2, h3 {{
        font-weight: 700;
        color: #FFFFFF;
    }}

    /* Tabs -- Robinhood-style underline tabs */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 4px;
        border-bottom: 1px solid {BORDER};
    }}

    .stTabs [data-baseweb="tab"] {{
        color: {MUTED_TEXT};
        font-weight: 600;
    }}

    .stTabs [aria-selected="true"] {{
        color: {ROBINHOOD_GREEN} !important;
        border-bottom: 2px solid {ROBINHOOD_GREEN} !important;
    }}

    /* Buttons -- rounded pill shape, green fill */
    /* Buttons -- Streamlit's own button styles can load after ours, so
    !important makes sure the green pill look always wins. */
    div[data-testid="stButton"] button {{
        background-color: {ROBINHOOD_GREEN} !important;
        color: #000000 !important;
        border: none !important;
        border-radius: 24px !important;
        font-weight: 700 !important;
        padding: 0.5rem 1.5rem !important;
    }}

    div[data-testid="stButton"] button:hover {{
        background-color: #00A804 !important;
        color: #000000 !important;
    }}

    div[data-testid="stButton"] button:focus:not(:active) {{
        color: #000000 !important;
    }}

    div[data-testid="stButton"] button p {{
        color: #000000 !important;
    }}

    /* Expanders -- dark "card" look, like a Robinhood list row */
    [data-testid="stExpander"] {{
        background-color: {CARD_BG};
        border: 1px solid {BORDER};
        border-radius: 12px;
    }}

    [data-testid="stExpander"] summary {{
        color: #FFFFFF;
        font-weight: 600;
    }}

    /* Text inputs, text areas & selectboxes -- dark cards */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div,
    .stNumberInput > div > div > input {{
        background-color: {CARD_BG};
        color: #FFFFFF;
        border: 1px solid {BORDER};
        border-radius: 8px;
    }}

    /* Captions / muted helper text */
    [data-testid="stCaptionContainer"] {{
        color: {MUTED_TEXT};
    }}

    /* Info / success / error boxes */
    [data-testid="stAlert"] {{
        border-radius: 12px;
        border: 1px solid {BORDER};
    }}

    hr {{
        border-color: {BORDER};
    }}
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------
# SECTION 1C: BIRTHDAY / ANNIVERSARY TEXT MESSAGES
# ------------------------------------------------------------------
# A handful of different short, personal-sounding messages for each
# occasion, instead of one single message that gets copy/pasted to
# everyone (which starts to feel robotic fast). Each person always gets
# the *same* one of these (based on their Planning Center ID), so the
# message on their card doesn't change every time you reopen the app --
# but different people are spread out across different messages.
#
# >>> TWEAK ME: add, remove, or reword any message below. Just keep the
# {first_name} and {pastor_name} (and {years_married}, for anniversaries)
# placeholders if you want those to still fill in automatically.

BIRTHDAY_MESSAGES = [
    "Happy birthday, {first_name}! Praying God blesses you in a special way this year. — {pastor_name}",
    "Hey {first_name}, happy birthday! So glad you're part of our church family. — {pastor_name}",
    "{first_name}, wishing you a great birthday today! Hope it's full of joy. — {pastor_name}",
    "Happy birthday, {first_name}! Thankful for you and excited to see what this year holds. — {pastor_name}",
    "Hey {first_name} — happy birthday! Hope you get to celebrate with people you love today. — {pastor_name}",
    "{first_name}, happy birthday! Praying you feel God's presence and peace in a fresh way this year. — {pastor_name}",
    "Happy birthday, {first_name}! Grateful for the gift you are to this church. — {pastor_name}",
    "Hey {first_name}, just a quick note to say happy birthday! Hope today is a good one. — {pastor_name}",
]

# Used when we don't know how many years the couple has been married yet.
ANNIVERSARY_MESSAGES = [
    "Happy anniversary, {first_name}! Celebrating God's faithfulness in your marriage today. — {pastor_name}",
    "Hey {first_name}, happy anniversary! So grateful for the example your marriage is to our church. — {pastor_name}",
    "{first_name}, wishing you and your spouse a joyful anniversary today! — {pastor_name}",
    "Happy anniversary, {first_name}! Praying for many more years of love and laughter together. — {pastor_name}",
    "Hey {first_name} — happy anniversary! Hope you get to celebrate well today. — {pastor_name}",
    "{first_name}, happy anniversary! Grateful to walk alongside you both in this season. — {pastor_name}",
    "Happy anniversary, {first_name}! Thankful for the love you two share. — {pastor_name}",
    "Hey {first_name}, happy anniversary today! Praying your marriage keeps pointing you both to Christ. — {pastor_name}",
]

# Used when we *do* know the number of years -- same idea, just with the
# year count worked naturally into the message. Use {years_ordinal} for
# "happy Xth anniversary" phrasing (1st, 2nd, 3rd, ...) and {years_word}
# for "X years"/"1 year" phrasing (so a first anniversary doesn't
# accidentally read "1 years").
ANNIVERSARY_MESSAGES_WITH_YEARS = [
    "Happy {years_ordinal} anniversary, {first_name}! Celebrating God's faithfulness through all these years. — {pastor_name}",
    "Hey {first_name}, {years_word} -- that's something worth celebrating! Happy anniversary. — {pastor_name}",
    "{first_name}, happy {years_ordinal} anniversary! Praying for many more years together. — {pastor_name}",
    "Happy anniversary, {first_name}! {years_word} of love is a beautiful thing to celebrate. — {pastor_name}",
    "Hey {first_name} — happy {years_ordinal} anniversary! So grateful for your marriage. — {pastor_name}",
    "{first_name}, {years_word} and still going strong! Happy anniversary. — {pastor_name}",
    "Happy {years_ordinal} anniversary, {first_name}! Thankful to see God's faithfulness in your marriage. — {pastor_name}",
    "Hey {first_name}, happy anniversary! {years_word} together is worth celebrating well today. — {pastor_name}",
]


def _ordinal(n):
    """Turn a number into its ordinal word, e.g. 1 -> '1st', 5 -> '5th',
    25 -> '25th' -- used so anniversary texts read naturally."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _pick_message(templates, seed_key):
    """Pick one message template out of a list, based on a stable 'seed'
    (like a person's ID) so the same person always lands on the same
    message -- but different people, with different IDs, get spread out
    across different messages instead of all getting an identical text.

    Uses a hash of the seed text (not Python's built-in hash(), which
    intentionally changes every time the app restarts) so the choice
    stays the same across reboots and redeploys, too.
    """
    digest = hashlib.md5(seed_key.encode()).hexdigest()
    index = int(digest, 16) % len(templates)
    return templates[index]


def birthday_message(person):
    """Build a ready-to-send, personalized birthday text for one person."""
    first_name = person["name"].split()[0] if person.get("name") else "there"
    template = _pick_message(BIRTHDAY_MESSAGES, person["id"] + "_bday")
    return template.format(first_name=first_name, pastor_name=PASTOR_NAME)


def anniversary_message(person):
    """Build a ready-to-send, personalized anniversary text for one
    person -- mentioning the number of years married, if we know it."""
    first_name = person["name"].split()[0] if person.get("name") else "there"
    years = person.get("years_married") or 0
    if years > 0:
        template = _pick_message(ANNIVERSARY_MESSAGES_WITH_YEARS, person["id"])
        years_word = "1 year" if years == 1 else f"{years} years"
        return template.format(
            first_name=first_name, pastor_name=PASTOR_NAME,
            years_ordinal=_ordinal(years), years_word=years_word,
        )
    template = _pick_message(ANNIVERSARY_MESSAGES, person["id"])
    return template.format(first_name=first_name, pastor_name=PASTOR_NAME)


# ------------------------------------------------------------------
# SECTION 2: PLANNING CENTER (PCO) HELPERS
# ------------------------------------------------------------------

def _pco_request(url, params=None):
    """Make one GET request to Planning Center, with basic handling for
    PCO's rate limit. A church with a lot of people/groups/check-ins can
    trigger a '429 Too Many Requests' when we page through a lot of data
    quickly -- if that happens, wait a moment and try again (up to 3
    times) before giving up.

    PCO Personal Access Tokens work as HTTP Basic Auth: the App ID is
    the username, the Secret is the password.
    """
    for attempt in range(3):
        response = requests.get(url, params=params, auth=(PCO_APP_ID, PCO_SECRET), timeout=15)
        if response.status_code == 429:
            wait_seconds = int(response.headers.get("Retry-After", 2))
            time.sleep(wait_seconds)
            continue
        response.raise_for_status()
        return response.json()

    response.raise_for_status()  # out of retries -- raise PCO's error
    return response.json()


def pco_get(path, params=None):
    """Make one GET request to a Planning Center path (relative to
    PCO_BASE_URL), e.g. pco_get("/people/v2/people")."""
    return _pco_request(f"{PCO_BASE_URL}{path}", params=params)


def search_people(name_query):
    """Search Planning Center for people whose name matches the query."""
    data = pco_get(
        "/people/v2/people",
        params={"where[search_name]": name_query, "include": "phone_numbers,emails"},
    )
    return _attach_included(data)


def list_all_people_with_birthdates():
    """Page through every person in Planning Center (100 at a time),
    collecting their name, birthdate, anniversary, and phone numbers."""
    people = []
    next_url = None
    params = {"include": "phone_numbers", "per_page": 100}

    while True:
        if next_url:
            # links.next from PCO already has all the query params baked in
            data = _pco_request(next_url)
        else:
            data = pco_get("/people/v2/people", params=params)

        people.extend(_attach_included(data))

        next_link = (data.get("links") or {}).get("next")
        if not next_link:
            break
        next_url = next_link

    return people


def _attach_included(data):
    """PCO returns phone numbers/emails as a separate 'included' list,
    linked back to each person. This stitches them together so each
    person dict already has its own phone numbers and emails."""
    included = data.get("included", [])
    people = []
    for person in data.get("data", []):
        person_id = person["id"]
        phone_numbers = [
            item["attributes"].get("number", "")
            for item in included
            if item.get("type") == "PhoneNumber" and _belongs_to(item, person_id)
        ]
        emails = [
            item["attributes"].get("address", "")
            for item in included
            if item.get("type") == "Email" and _belongs_to(item, person_id)
        ]
        people.append({
            "id": person_id,
            "name": person["attributes"].get("name", "(no name)"),
            "birthdate": person["attributes"].get("birthdate"),
            "anniversary": person["attributes"].get("anniversary"),
            "grade": person["attributes"].get("grade"),
            "child": person["attributes"].get("child", False),
            "phone_numbers": [p for p in phone_numbers if p],
            "emails": [e for e in emails if e],
        })
    return people


def _belongs_to(included_item, person_id):
    rel = (included_item.get("relationships") or {}).get("person", {}).get("data") or {}
    return rel.get("id") == person_id


def age_category(person):
    """Sort a person into one of four ministry age groups:
      - Preschool: birth through Kindergarten
      - Children:  1st through 5th grade
      - Youth:     6th through 12th grade
      - Adults:    everyone else

    This uses Planning Center's 'grade' field, which is normally
    numbered Kindergarten = 0, 1st grade = 1, ... 12th grade = 12, with
    preschool tiers as numbers below 0.

    # >>> TWEAK ME: some churches customize this numbering under
    # Account -> Localization -> Grades in Planning Center. If ages look
    # sorted into the wrong group, adjust the cutoffs below to match
    # your church's actual grade numbers.

    If someone has no grade on file at all, we fall back to Planning
    Center's 'child' checkbox: a child with no grade yet is counted as
    Preschool, everyone else defaults to Adults.
    """
    grade = person.get("grade")
    if grade is not None:
        if grade <= 0:
            return "Preschool"
        if grade <= 5:
            return "Children"
        if grade <= 12:
            return "Youth"
        return "Adults"
    return "Preschool" if person.get("child") else "Adults"


def upcoming_birthdays(people, days_ahead=BIRTHDAY_LOOKAHEAD_DAYS):
    """Filter a list of people down to just the ones with a birthday
    in the next `days_ahead` days, soonest first."""
    today = datetime.date.today()
    upcoming = []
    for person in people:
        if not person.get("birthdate"):
            continue
        try:
            bday = datetime.datetime.strptime(person["birthdate"], "%Y-%m-%d").date()
        except ValueError:
            continue

        try:
            next_bday = bday.replace(year=today.year)
        except ValueError:
            # Feb 29 in a non-leap year -- celebrate on Feb 28 instead
            next_bday = bday.replace(year=today.year, day=28)
        if next_bday < today:
            try:
                next_bday = next_bday.replace(year=today.year + 1)
            except ValueError:
                next_bday = next_bday.replace(year=today.year + 1, day=28)

        days_until = (next_bday - today).days
        if 0 <= days_until <= days_ahead:
            person_copy = dict(person)
            person_copy["days_until"] = days_until
            person_copy["next_birthday"] = next_bday
            upcoming.append(person_copy)

    upcoming.sort(key=lambda p: p["days_until"])
    return upcoming


def upcoming_anniversaries(people, days_ahead=ANNIVERSARY_LOOKAHEAD_DAYS):
    """Filter a list of people down to just the ones with a wedding
    anniversary in the next `days_ahead` days, soonest first. Works just
    like upcoming_birthdays() above, but looks at the 'anniversary' date
    Planning Center stores for each person instead of their birthdate."""
    today = datetime.date.today()
    upcoming = []
    for person in people:
        if not person.get("anniversary"):
            continue
        try:
            anniv = datetime.datetime.strptime(person["anniversary"], "%Y-%m-%d").date()
        except ValueError:
            continue

        try:
            next_anniv = anniv.replace(year=today.year)
        except ValueError:
            # Feb 29 in a non-leap year -- celebrate on Feb 28 instead
            next_anniv = anniv.replace(year=today.year, day=28)
        if next_anniv < today:
            try:
                next_anniv = next_anniv.replace(year=today.year + 1)
            except ValueError:
                next_anniv = next_anniv.replace(year=today.year + 1, day=28)

        days_until = (next_anniv - today).days
        if 0 <= days_until <= days_ahead:
            person_copy = dict(person)
            person_copy["days_until"] = days_until
            person_copy["next_anniversary"] = next_anniv
            person_copy["years_married"] = next_anniv.year - anniv.year
            upcoming.append(person_copy)

    upcoming.sort(key=lambda p: p["days_until"])
    return upcoming


@st.cache_data(ttl=300)  # remembers the result for 5 minutes so we don't hammer the API
def _cached_all_people():
    return list_all_people_with_birthdates()


def get_person_details(person_id):
    """Look up one person's phone numbers, grade, and child flag by
    their Planning Center ID -- used by tabs that only get a person's
    ID (not their full contact info) from another endpoint, such as
    Workflow cards or Check-Ins, so they can still offer texting and
    age-group filtering."""
    data = pco_get(f"/people/v2/people/{person_id}", params={"include": "phone_numbers"})
    attrs = data.get("data", {}).get("attributes", {})
    included = data.get("included", [])
    phone_numbers = [
        item["attributes"].get("number", "")
        for item in included
        if item.get("type") == "PhoneNumber" and item["attributes"].get("number")
    ]
    return {
        "phone_numbers": phone_numbers,
        "grade": attrs.get("grade"),
        "child": attrs.get("child", False),
    }


def get_my_person_id():
    """Find out which Planning Center person the API keys belong to
    (whoever created the Personal Access Token)."""
    data = pco_get("/people/v2/me")
    return data["data"]["id"]


def get_my_workflow_cards():
    """Pull every Workflow card assigned to whoever owns these API keys,
    across every workflow -- sorted so overdue cards show up first, then
    soonest-due next. Workflows are PCO's built-in follow-up system, so
    this is the church's real to-do list of people to check in on."""
    my_id = get_my_person_id()
    cards = []
    next_url = None
    params = {"filter": "assigned", "include": "person,workflow", "per_page": 100}

    while True:
        if next_url:
            # links.next from PCO already has all the query params baked in
            data = _pco_request(next_url)
        else:
            data = pco_get(f"/people/v2/people/{my_id}/workflow_cards", params=params)

        # 'included' holds the full Person/Workflow records this page
        # referenced, keyed by (type, id) so we can look them up below.
        included_by_key = {
            (item["type"], item["id"]): item for item in data.get("included", [])
        }

        for card in data.get("data", []):
            attrs = card["attributes"]
            if attrs.get("completed_at") or attrs.get("removed_at"):
                continue  # already finished or removed -- nothing to follow up on

            relationships = card.get("relationships", {})
            person_ref = (relationships.get("person") or {}).get("data") or {}
            workflow_ref = (relationships.get("workflow") or {}).get("data") or {}
            person_item = included_by_key.get(("Person", person_ref.get("id"))) or {}
            workflow_item = included_by_key.get(("Workflow", workflow_ref.get("id"))) or {}

            cards.append({
                "card_id": card["id"],
                "person_id": person_ref.get("id"),
                "person_name": person_item.get("attributes", {}).get("name", "(unknown person)"),
                "grade": person_item.get("attributes", {}).get("grade"),
                "child": person_item.get("attributes", {}).get("child", False),
                "workflow_name": workflow_item.get("attributes", {}).get("name", "(a workflow)"),
                "stage": attrs.get("stage"),
                "overdue": bool(attrs.get("overdue")),
                "due_at": attrs.get("calculated_due_at"),
            })

        next_link = (data.get("links") or {}).get("next")
        if not next_link:
            break
        next_url = next_link

    # Overdue cards first; within each group, soonest due date first.
    # Cards with no due date at all sort to the very end.
    cards.sort(key=lambda c: (not c["overdue"], c["due_at"] or "9999-12-31"))
    return cards


@st.cache_data(ttl=300)  # remembers the result for 5 minutes so we don't hammer the API
def _cached_my_workflow_cards():
    return get_my_workflow_cards()


def get_drifting_regulars():
    """Look at recent Check-Ins attendance to find people who used to
    come consistently but have gone quiet lately -- so nobody slips
    away unnoticed.

    How "drifting" is decided (see the TWEAK ME settings up top):
      1. Look back DRIFT_LOOKBACK_DAYS days of check-ins, church-wide.
      2. Anyone with DRIFT_MIN_CHECKINS or more check-ins in that
         window counts as a "regular".
      3. If a regular's most recent check-in was more than
         DRIFT_THRESHOLD_DAYS days ago, they're flagged as drifting.
    """
    cutoff = datetime.date.today() - datetime.timedelta(days=DRIFT_LOOKBACK_DAYS)
    people_seen = {}  # person_id -> {"name", "count", "last_seen"}

    next_url = None
    params = {"order": "-created_at", "per_page": 100}
    check_ins_url = f"{PCO_BASE_URL}/check-ins/v2/check_ins"

    while True:
        if next_url:
            data = _pco_request(next_url)
        else:
            data = _pco_request(check_ins_url, params=params)

        reached_cutoff = False
        for item in data.get("data", []):
            created_at = item["attributes"].get("created_at") or ""
            try:
                created_date = datetime.datetime.strptime(created_at[:10], "%Y-%m-%d").date()
            except ValueError:
                continue

            # Check-ins come back newest-first, so once we hit one older
            # than our lookback window we can stop paging entirely.
            if created_date < cutoff:
                reached_cutoff = True
                break

            person_ref = (item.get("relationships", {}).get("person") or {}).get("data")
            if not person_ref:
                continue  # a one-time guest check-in with no linked person record

            person_id = person_ref["id"]
            first = item["attributes"].get("first_name") or ""
            last = item["attributes"].get("last_name") or ""
            name = (first + " " + last).strip() or "(unknown)"

            record = people_seen.setdefault(
                person_id, {"name": name, "count": 0, "last_seen": created_date}
            )
            record["count"] += 1
            if created_date > record["last_seen"]:
                record["last_seen"] = created_date

        if reached_cutoff:
            break

        next_link = (data.get("links") or {}).get("next")
        if not next_link:
            break
        next_url = next_link

    today = datetime.date.today()
    drifting = []
    for person_id, info in people_seen.items():
        if info["count"] < DRIFT_MIN_CHECKINS:
            continue  # wasn't attending regularly to begin with
        days_since = (today - info["last_seen"]).days
        if days_since >= DRIFT_THRESHOLD_DAYS:
            drifting.append({
                "person_id": person_id,
                "name": info["name"],
                "last_seen": info["last_seen"],
                "days_since": days_since,
                "check_in_count": info["count"],
            })

    drifting.sort(key=lambda p: -p["days_since"])  # longest-gone first
    return drifting


@st.cache_data(ttl=900)  # attendance patterns change slowly -- cache for 15 minutes
def _cached_drifting_regulars():
    return get_drifting_regulars()


def get_new_people(days_back=NEW_GUEST_LOOKBACK_DAYS):
    """People whose Planning Center profile was created recently --
    likely a brand-new guest or new member the office just added.
    PCO has a built-in filter for this, so we just ask for it directly."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days_back)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    data = pco_get(
        "/people/v2/people",
        params={
            "filter": "created_since",
            "time": cutoff_iso,
            "include": "phone_numbers",
            "order": "-created_at",
            "per_page": 100,
        },
    )
    return _attach_included(data)


@st.cache_data(ttl=600)
def _cached_new_people():
    return get_new_people()


def get_first_time_check_ins(days_back=NEW_GUEST_LOOKBACK_DAYS):
    """People who checked in for the very first time recently -- likely
    a first-time guest at a service or event. PCO flags these for us
    with the 'first_time' filter, so no extra math is needed here."""
    cutoff = datetime.date.today() - datetime.timedelta(days=days_back)
    first_timers = []
    next_url = None
    params = {"filter": "first_time", "order": "-created_at", "per_page": 100}
    check_ins_url = f"{PCO_BASE_URL}/check-ins/v2/check_ins"

    while True:
        if next_url:
            data = _pco_request(next_url)
        else:
            data = _pco_request(check_ins_url, params=params)

        reached_cutoff = False
        for item in data.get("data", []):
            created_at = item["attributes"].get("created_at") or ""
            try:
                created_date = datetime.datetime.strptime(created_at[:10], "%Y-%m-%d").date()
            except ValueError:
                continue

            if created_date < cutoff:
                reached_cutoff = True
                break

            person_ref = (item.get("relationships", {}).get("person") or {}).get("data")
            if not person_ref:
                continue  # a one-time guest with no linked person record

            first = item["attributes"].get("first_name") or ""
            last = item["attributes"].get("last_name") or ""
            first_timers.append({
                "person_id": person_ref["id"],
                "name": (first + " " + last).strip() or "(unknown)",
                "checked_in_on": created_date,
            })

        if reached_cutoff:
            break

        next_link = (data.get("links") or {}).get("next")
        if not next_link:
            break
        next_url = next_link

    first_timers.sort(key=lambda p: p["checked_in_on"], reverse=True)  # most recent first
    return first_timers


@st.cache_data(ttl=600)
def _cached_first_time_check_ins():
    return get_first_time_check_ins()


def _group_member_ids(group_id):
    """All person IDs with a membership in one specific Group."""
    ids = set()
    next_url = None
    params = {"per_page": 100}

    while True:
        if next_url:
            data = _pco_request(next_url)
        else:
            data = pco_get(f"/groups/v2/groups/{group_id}/memberships", params=params)

        for membership in data.get("data", []):
            person_ref = (membership.get("relationships", {}).get("person") or {}).get("data")
            if person_ref:
                ids.add(person_ref["id"])

        next_link = (data.get("links") or {}).get("next")
        if not next_link:
            break
        next_url = next_link

    return ids


def get_people_not_in_a_group():
    """Find everyone in the church database who isn't currently a member
    of any Group -- a simple signal for who might be worth inviting into
    a small group or community."""
    connected_ids = set()
    next_url = None
    params = {"where[archive_status]": "not_archived", "per_page": 100}

    while True:
        if next_url:
            groups_data = _pco_request(next_url)
        else:
            groups_data = pco_get("/groups/v2/groups", params=params)

        for group in groups_data.get("data", []):
            connected_ids |= _group_member_ids(group["id"])
            time.sleep(0.1)  # a small pause so a church with many groups doesn't trip PCO's rate limit

        next_link = (groups_data.get("links") or {}).get("next")
        if not next_link:
            break
        next_url = next_link

    all_people = _cached_all_people()
    ungrouped = [p for p in all_people if p["id"] not in connected_ids]
    ungrouped.sort(key=lambda p: p["name"].lower())
    return ungrouped


@st.cache_data(ttl=1800)  # group membership doesn't change minute to minute
def _cached_people_not_in_a_group():
    return get_people_not_in_a_group()


def get_my_upcoming_schedules():
    """Upcoming Planning Center Services plans (services, rehearsals,
    etc.) that whoever owns these API keys is scheduled to serve at."""
    my_id = get_my_person_id()
    data = pco_get(
        f"/services/v2/people/{my_id}/schedules",
        params={"filter": "future", "order": "starts_at", "per_page": 100},
    )
    schedules = []
    for item in data.get("data", []):
        attrs = item["attributes"]
        schedules.append({
            "schedule_id": item["id"],
            "service_type_name": attrs.get("service_type_name") or "(a service)",
            "team_position_name": attrs.get("team_position_name"),
            "dates": attrs.get("dates") or attrs.get("short_dates"),
            "status": attrs.get("status"),
        })
    return schedules


@st.cache_data(ttl=600)
def _cached_my_upcoming_schedules():
    return get_my_upcoming_schedules()


# ------------------------------------------------------------------
# SECTION 3: CLEARSTREAM HELPERS
# ------------------------------------------------------------------

def clearstream_headers():
    return {"X-Api-Key": CLEARSTREAM_API_KEY, "Content-Type": "application/json"}


def to_e164(raw_number):
    """Best-effort cleanup of a phone number into E.164 format
    (e.g. +12515550100), which is what Clearstream requires.
    Assumes a US number unless it already starts with '+'."""
    if not raw_number:
        return None
    digits = "".join(ch for ch in raw_number if ch.isdigit())
    if raw_number.strip().startswith("+"):
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return None  # couldn't confidently format it -- let the caller know


def send_text(to_number, message_body):
    """Start (or continue) a Clearstream conversation thread with one
    person. Threads are used instead of one-off texts because replies
    land back in the Clearstream inbox -- important for pastoral care.

    NOTE: Clearstream will not deliver to anyone who has opted out.
    That's enforced on their end, which is exactly what we want.
    """
    formatted_number = to_e164(to_number)
    if not formatted_number:
        return False, f"Couldn't format '{to_number}' as a phone number."

    payload = {
        "mobile_number": formatted_number,
        "reply_header": CHURCH_NAME,
        "reply_body": message_body,
    }
    response = requests.post(
        f"{CLEARSTREAM_BASE_URL}/threads",
        json=payload,
        headers=clearstream_headers(),
        timeout=15,
    )
    if response.status_code in (200, 201):
        return True, "Text sent!"
    return False, f"Clearstream error ({response.status_code}): {response.text}"


def get_recent_threads(limit=INBOX_LIMIT):
    response = requests.get(
        f"{CLEARSTREAM_BASE_URL}/threads",
        params={"limit": limit},
        headers=clearstream_headers(),
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


# ------------------------------------------------------------------
# SECTION 4: REUSABLE UI PIECES
# ------------------------------------------------------------------

def send_text_box(person_name, phone_numbers, key_prefix, default_message=None):
    """A small 'send a text' box: pick a number (if there's more than
    one on file), type a message, hit Send.

    Pass in `default_message` (e.g. from birthday_message() or
    anniversary_message()) to pre-fill something more personal than the
    plain "Hi {first_name}!" fallback -- it's still fully editable before
    sending."""
    if not phone_numbers:
        st.caption("No phone number on file.")
        return

    chosen_number = phone_numbers[0]
    if len(phone_numbers) > 1:
        chosen_number = st.selectbox("Phone number", phone_numbers, key=f"{key_prefix}_number")

    if default_message is None:
        first_name = person_name.split()[0] if person_name else "there"
        default_message = f"Hi {first_name}! "

    message = st.text_area(
        "Message", value=default_message, key=f"{key_prefix}_msg"
    )

    if st.button("Send text", key=f"{key_prefix}_send"):
        ok, info = send_text(chosen_number, message)
        if ok:
            st.success(info)
        else:
            st.error(info)


def age_group_filter(people, key_prefix):
    """Show the 'Age group' dropdown (Preschool / Children / Youth /
    Adults / All ages) and return only the people in whichever group
    was picked. Every person dict passed in needs a 'grade' and 'child'
    key (see age_category() in Section 2) for this to sort correctly."""
    choice = st.selectbox(
        "Age group", ["All ages"] + AGE_CATEGORIES, key=f"{key_prefix}_age_filter"
    )
    if choice == "All ages":
        return people
    return [p for p in people if age_category(p) == choice]


# ------------------------------------------------------------------
# SECTION 5: THE PAGE ITSELF
# ------------------------------------------------------------------

st.title(f"{CHURCH_NAME} Care Dashboard")

missing_secrets = [
    name for name, value in [
        ("PCO_APP_ID", PCO_APP_ID),
        ("PCO_SECRET", PCO_SECRET),
        ("CLEARSTREAM_API_KEY", CLEARSTREAM_API_KEY),
    ] if not value
]
if missing_secrets:
    st.error(
        "Missing secret(s): " + ", ".join(missing_secrets) +
        ". Add these in Replit's Secrets tab (lock icon in the left sidebar), "
        "then click Run again."
    )
    st.stop()

(
    tab_birthdays, tab_anniversaries, tab_followup, tab_drifting, tab_new_guests,
    tab_connection_gaps, tab_my_schedule, tab_find_person, tab_inbox,
) = st.tabs([
    "🎂 Birthdays", "💍 Anniversaries", "📋 Follow-up Queue", "📉 Drifting Regulars",
    "🙌 New & Returning Guests", "🧩 Connection Gaps", "🗓️ My Serving Schedule",
    "🔍 Find a Person", "💬 Texting Inbox",
])

# --- Tab 1: Birthdays --------------------------------------------------
with tab_birthdays:
    st.subheader(f"Birthdays in the next {BIRTHDAY_LOOKAHEAD_DAYS} days")

    if st.button("Refresh birthdays"):
        st.cache_data.clear()

    try:
        with st.spinner("Loading people from Planning Center..."):
            all_people = _cached_all_people()
    except requests.exceptions.RequestException as e:
        st.error(f"Couldn't reach Planning Center: {e}")
        all_people = []

    birthday_people = upcoming_birthdays(all_people)
    birthday_people = age_group_filter(birthday_people, key_prefix="bday")

    if not birthday_people:
        st.info("No birthdays in the next week.")

    for person in birthday_people:
        label = f"{person['name']} — {person['next_birthday'].strftime('%b %d')} ({person['days_until']} days)"
        with st.expander(label):
            send_text_box(
                person["name"], person["phone_numbers"], key_prefix=f"bday_{person['id']}",
                default_message=birthday_message(person),
            )

# --- Tab 2: Anniversaries -------------------------------------------------
with tab_anniversaries:
    st.subheader(f"Anniversaries in the next {ANNIVERSARY_LOOKAHEAD_DAYS} days")

    if st.button("Refresh anniversaries"):
        st.cache_data.clear()

    try:
        with st.spinner("Loading people from Planning Center..."):
            all_people = _cached_all_people()
    except requests.exceptions.RequestException as e:
        st.error(f"Couldn't reach Planning Center: {e}")
        all_people = []

    anniversary_people = upcoming_anniversaries(all_people)
    anniversary_people = age_group_filter(anniversary_people, key_prefix="anniv")

    if not anniversary_people:
        st.info("No anniversaries in the next week.")

    for person in anniversary_people:
        years_bit = f", {person['years_married']} years" if person["years_married"] > 0 else ""
        label = (
            f"{person['name']} — {person['next_anniversary'].strftime('%b %d')} "
            f"({person['days_until']} days{years_bit})"
        )
        with st.expander(label):
            send_text_box(
                person["name"], person["phone_numbers"], key_prefix=f"anniv_{person['id']}",
                default_message=anniversary_message(person),
            )

# --- Tab 3: Follow-up Queue -----------------------------------------------
with tab_followup:
    st.subheader("Workflow cards assigned to you")
    st.caption("Pulled from Planning Center Workflows -- overdue cards show up first.")

    if st.button("Refresh follow-ups"):
        st.cache_data.clear()

    try:
        with st.spinner("Loading your workflow cards..."):
            my_cards = _cached_my_workflow_cards()
    except requests.exceptions.RequestException as e:
        st.error(f"Couldn't reach Planning Center: {e}")
        my_cards = []

    my_cards = age_group_filter(my_cards, key_prefix="followup")

    if not my_cards:
        st.info("Nothing assigned to you right now -- nice and clear!")

    for card in my_cards:
        due_bit = f" — due {card['due_at'][:10]}" if card["due_at"] else ""
        overdue_bit = " ⚠️ OVERDUE" if card["overdue"] else ""
        label = f"{card['person_name']} — {card['workflow_name']} ({card['stage']}){due_bit}{overdue_bit}"
        with st.expander(label):
            try:
                phone_numbers = get_person_details(card["person_id"])["phone_numbers"] if card["person_id"] else []
            except requests.exceptions.RequestException:
                phone_numbers = []
            send_text_box(card["person_name"], phone_numbers, key_prefix=f"followup_{card['card_id']}")

# --- Tab 4: Drifting Regulars ----------------------------------------------
with tab_drifting:
    st.subheader("People who may be drifting away")
    st.caption(
        f"People with {DRIFT_MIN_CHECKINS}+ check-ins in the last {DRIFT_LOOKBACK_DAYS} days, "
        f"but none in the last {DRIFT_THRESHOLD_DAYS} days."
    )

    if st.button("Refresh drifting list"):
        st.cache_data.clear()

    try:
        with st.spinner("Looking at recent Check-Ins attendance..."):
            drifting_people = _cached_drifting_regulars()
    except requests.exceptions.RequestException as e:
        st.error(f"Couldn't reach Planning Center: {e}")
        drifting_people = []

    # Check-Ins doesn't give us grade/child directly, so look each person
    # up once here (this also fetches their phone number, so it's reused
    # below instead of asking Planning Center for it twice).
    enriched_drifting_people = []
    for person in drifting_people:
        try:
            details = get_person_details(person["person_id"])
        except requests.exceptions.RequestException:
            details = {"phone_numbers": [], "grade": None, "child": False}
        enriched_drifting_people.append({**person, **details})
    drifting_people = age_group_filter(enriched_drifting_people, key_prefix="drift")

    if not drifting_people:
        st.info("No one looks like they're drifting right now.")

    for person in drifting_people:
        label = (
            f"{person['name']} — last seen {person['last_seen'].strftime('%b %d')} "
            f"({person['days_since']} days ago)"
        )
        with st.expander(label):
            st.caption(f"Checked in {person['check_in_count']} times in the last {DRIFT_LOOKBACK_DAYS} days.")
            send_text_box(person["name"], person["phone_numbers"], key_prefix=f"drift_{person['person_id']}")

# --- Tab 5: New & Returning Guests ---------------------------------------
with tab_new_guests:
    st.subheader("New & returning guests")
    st.caption(f"Planning Center activity from the last {NEW_GUEST_LOOKBACK_DAYS} days.")

    if st.button("Refresh guests"):
        st.cache_data.clear()

    st.markdown("**New profiles added**")
    try:
        with st.spinner("Checking for new profiles..."):
            new_people = _cached_new_people()
    except requests.exceptions.RequestException as e:
        st.error(f"Couldn't reach Planning Center: {e}")
        new_people = []

    new_people = age_group_filter(new_people, key_prefix="newperson")

    if not new_people:
        st.caption("No new profiles recently.")
    for person in new_people:
        with st.expander(person["name"]):
            send_text_box(person["name"], person["phone_numbers"], key_prefix=f"newperson_{person['id']}")

    st.divider()
    st.markdown("**First-time check-ins**")
    try:
        with st.spinner("Checking recent first-time check-ins..."):
            first_timers = _cached_first_time_check_ins()
    except requests.exceptions.RequestException as e:
        st.error(f"Couldn't reach Planning Center: {e}")
        first_timers = []

    # Check-Ins doesn't give us grade/child directly, so look each guest
    # up once here (this also fetches their phone number, so it's reused
    # below instead of asking Planning Center for it twice).
    enriched_first_timers = []
    for guest in first_timers:
        try:
            details = get_person_details(guest["person_id"])
        except requests.exceptions.RequestException:
            details = {"phone_numbers": [], "grade": None, "child": False}
        enriched_first_timers.append({**guest, **details})
    first_timers = age_group_filter(enriched_first_timers, key_prefix="firsttime")

    if not first_timers:
        st.caption("No first-time check-ins recently.")
    for guest in first_timers:
        label = f"{guest['name']} — checked in {guest['checked_in_on'].strftime('%b %d')}"
        with st.expander(label):
            send_text_box(guest["name"], guest["phone_numbers"], key_prefix=f"firsttime_{guest['person_id']}")

# --- Tab 6: Connection Gaps ------------------------------------------------
with tab_connection_gaps:
    st.subheader("People not currently in a Group")
    st.caption("A simple list of who might be worth inviting into a small group or community.")

    if st.button("Refresh connection gaps"):
        st.cache_data.clear()

    try:
        with st.spinner("Comparing the People database against Group memberships..."):
            ungrouped_people = _cached_people_not_in_a_group()
    except requests.exceptions.RequestException as e:
        st.error(f"Couldn't reach Planning Center: {e}")
        ungrouped_people = []

    ungrouped_people = age_group_filter(ungrouped_people, key_prefix="gap")

    st.caption(f"{len(ungrouped_people)} people are not in any Group.")

    # This list can be long, so we only show a batch at a time (see the
    # CONNECTION_GAPS_PAGE_SIZE setting up top) with a "Show more" button,
    # instead of rendering thousands of cards at once.
    if "connection_gaps_shown" not in st.session_state:
        st.session_state.connection_gaps_shown = CONNECTION_GAPS_PAGE_SIZE

    shown_count = st.session_state.connection_gaps_shown
    for person in ungrouped_people[:shown_count]:
        with st.expander(person["name"]):
            send_text_box(person["name"], person["phone_numbers"], key_prefix=f"gap_{person['id']}")

    if shown_count < len(ungrouped_people):
        st.caption(f"Showing {min(shown_count, len(ungrouped_people))} of {len(ungrouped_people)}.")
        if st.button("Show more"):
            st.session_state.connection_gaps_shown += CONNECTION_GAPS_PAGE_SIZE
            st.rerun()

# --- Tab 7: My Serving Schedule ---------------------------------------------
with tab_my_schedule:
    st.subheader("Your upcoming serving schedule")
    st.caption("Services plans you're scheduled for, soonest first.")

    if st.button("Refresh my schedule"):
        st.cache_data.clear()

    try:
        with st.spinner("Loading your schedule from Planning Center Services..."):
            my_schedules = _cached_my_upcoming_schedules()
    except requests.exceptions.RequestException as e:
        st.error(f"Couldn't reach Planning Center Services: {e}")
        my_schedules = []

    if not my_schedules:
        st.info("Nothing on your serving schedule right now.")

    for item in my_schedules:
        position_bit = f" — {item['team_position_name']}" if item["team_position_name"] else ""
        status_bit = f" ({item['status']})" if item["status"] else ""
        st.write(f"**{item['dates']}** — {item['service_type_name']}{position_bit}{status_bit}")
        st.divider()

# --- Tab 8: Find a Person -----------------------------------------------
with tab_find_person:
    st.subheader("Search Planning Center by name")
    query = st.text_input("Name", placeholder="e.g. Jane Smith")

    if query:
        try:
            with st.spinner("Searching..."):
                results = search_people(query)
        except requests.exceptions.RequestException as e:
            st.error(f"Couldn't reach Planning Center: {e}")
            results = []

        results = age_group_filter(results, key_prefix="find")

        if not results:
            st.info("No matches found.")

        for person in results:
            with st.expander(person["name"]):
                if person["emails"]:
                    st.caption("Email: " + ", ".join(person["emails"]))
                send_text_box(person["name"], person["phone_numbers"], key_prefix=f"find_{person['id']}")

# --- Tab 9: Texting Inbox -------------------------------------------------
with tab_inbox:
    st.subheader("Recent texting conversations")

    if st.button("Refresh inbox"):
        st.cache_data.clear()

    try:
        with st.spinner("Loading from Clearstream..."):
            inbox_data = get_recent_threads()
    except requests.exceptions.RequestException as e:
        st.error(f"Couldn't reach Clearstream: {e}")
        inbox_data = {"data": []}

    threads = inbox_data.get("data", [])
    if not threads:
        st.info("No recent conversations.")

    for thread in threads:
        # Clearstream threads look like:
        #   {"subscriber": {"first": ..., "last": ..., "mobile_number": ...},
        #    "related_message": {"text": {"full": ...}}, ...}
        subscriber = thread.get("subscriber") or {}
        first = subscriber.get("first") or ""
        last = subscriber.get("last") or ""
        name = (first + " " + last).strip() or subscriber.get("mobile_number") or "Unknown"

        related_message = thread.get("related_message") or {}
        message_text = related_message.get("text") or {}
        last_message = message_text.get("full") or message_text.get("body") or ""

        st.write(f"**{name}** — {last_message}")
        st.divider()


# ------------------------------------------------------------------
# SECTION 6: WHAT'S BUILT
# ------------------------------------------------------------------
# All phases from COWORK-PROJECT-BRIEF.md, Section 7, are now built:
#   Phase 1 - Birthdays, Find a Person, Texting Inbox
#   Phase 2 - Follow-up Queue (Workflow cards assigned to the owner)
#   Phase 3 - Drifting Regulars (Check-Ins attendance gaps)
#   Phase 4 - New & Returning Guests, Connection Gaps, My Serving Schedule
#
# Nothing left on the original roadmap -- future ideas can go here.
