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
  2. Planning Center    -- talking to the PCO API
  3. Clearstream        -- talking to the Clearstream API
  4. Reusable UI pieces -- the "send a text" box
  5. The actual page    -- the five tabs
  6. Future hooks       -- notes for Phase 4 (not built yet)

Look for "# >>> TWEAK ME" comments -- those are safe, simple
settings you can change without breaking anything else.
============================================================
"""

import os
import datetime
import requests
import streamlit as st

# ------------------------------------------------------------------
# SECTION 1: SETTINGS
# ------------------------------------------------------------------

# >>> TWEAK ME: how many days ahead counts as an "upcoming" birthday
BIRTHDAY_LOOKAHEAD_DAYS = 7

# >>> TWEAK ME: how many recent texting conversations to show in the inbox
INBOX_LIMIT = 30

# >>> TWEAK ME: how many days back to look when deciding who's a "regular"
DRIFT_LOOKBACK_DAYS = 60

# >>> TWEAK ME: how many check-ins within that window counts as "regular attendance"
DRIFT_MIN_CHECKINS = 3

# >>> TWEAK ME: if a regular hasn't checked in for this many days, flag them as drifting
DRIFT_THRESHOLD_DAYS = 21

# Secrets come from your host's Secrets manager -- never type real keys
# directly into this file.
PCO_APP_ID = os.environ.get("PCO_APP_ID", "")
PCO_SECRET = os.environ.get("PCO_SECRET", "")
CLEARSTREAM_API_KEY = os.environ.get("CLEARSTREAM_API_KEY", "")
CHURCH_NAME = os.environ.get("CHURCH_NAME", "Our Church")

PCO_BASE_URL = "https://api.planningcenteronline.com"
CLEARSTREAM_BASE_URL = "https://api.getclearstream.com/v1"

st.set_page_config(page_title="Church Care Dashboard", page_icon="✝️", layout="wide")


# ------------------------------------------------------------------
# SECTION 2: PLANNING CENTER (PCO) HELPERS
# ------------------------------------------------------------------

def pco_get(path, params=None):
    """Make one GET request to Planning Center.

    PCO Personal Access Tokens work as HTTP Basic Auth: the App ID is
    the username, the Secret is the password.
    """
    url = f"{PCO_BASE_URL}{path}"
    response = requests.get(url, params=params, auth=(PCO_APP_ID, PCO_SECRET), timeout=15)
    response.raise_for_status()
    return response.json()


def search_people(name_query):
    """Search Planning Center for people whose name matches the query."""
    data = pco_get(
        "/people/v2/people",
        params={"where[search_name]": name_query, "include": "phone_numbers,emails"},
    )
    return _attach_included(data)


def list_all_people_with_birthdates():
    """Page through every person in Planning Center (100 at a time),
    collecting their name, birthdate, and phone numbers."""
    people = []
    next_url = None
    params = {"include": "phone_numbers", "per_page": 100}

    while True:
        if next_url:
            # links.next from PCO already has all the query params baked in
            response = requests.get(next_url, auth=(PCO_APP_ID, PCO_SECRET), timeout=15)
            response.raise_for_status()
            data = response.json()
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
            "phone_numbers": [p for p in phone_numbers if p],
            "emails": [e for e in emails if e],
        })
    return people


def _belongs_to(included_item, person_id):
    rel = (included_item.get("relationships") or {}).get("person", {}).get("data") or {}
    return rel.get("id") == person_id


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


@st.cache_data(ttl=300)  # remembers the result for 5 minutes so we don't hammer the API
def _cached_all_people():
    return list_all_people_with_birthdates()


def get_person_phone_numbers(person_id):
    """Look up one person's phone numbers by their Planning Center ID.
    Used by the Follow-up Queue and Drifting Regulars tabs, which only
    get a person's ID (not their full contact info) from other endpoints."""
    data = pco_get(f"/people/v2/people/{person_id}", params={"include": "phone_numbers"})
    included = data.get("included", [])
    return [
        item["attributes"].get("number", "")
        for item in included
        if item.get("type") == "PhoneNumber" and item["attributes"].get("number")
    ]


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
            response = requests.get(next_url, auth=(PCO_APP_ID, PCO_SECRET), timeout=15)
            response.raise_for_status()
            data = response.json()
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
            response = requests.get(next_url, auth=(PCO_APP_ID, PCO_SECRET), timeout=15)
        else:
            response = requests.get(check_ins_url, params=params, auth=(PCO_APP_ID, PCO_SECRET), timeout=15)
        response.raise_for_status()
        data = response.json()

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

def send_text_box(person_name, phone_numbers, key_prefix):
    """A small 'send a text' box: pick a number (if there's more than
    one on file), type a message, hit Send."""
    if not phone_numbers:
        st.caption("No phone number on file.")
        return

    chosen_number = phone_numbers[0]
    if len(phone_numbers) > 1:
        chosen_number = st.selectbox("Phone number", phone_numbers, key=f"{key_prefix}_number")

    first_name = person_name.split()[0] if person_name else "there"
    message = st.text_input(
        "Message", value=f"Hi {first_name}! ", key=f"{key_prefix}_msg"
    )

    if st.button("Send text", key=f"{key_prefix}_send"):
        ok, info = send_text(chosen_number, message)
        if ok:
            st.success(info)
        else:
            st.error(info)


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

tab_birthdays, tab_followup, tab_drifting, tab_find_person, tab_inbox = st.tabs(
    ["🎂 Birthdays", "📋 Follow-up Queue", "📉 Drifting Regulars", "🔍 Find a Person", "💬 Texting Inbox"]
)

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

    if not birthday_people:
        st.info("No birthdays in the next week.")

    for person in birthday_people:
        label = f"{person['name']} — {person['next_birthday'].strftime('%b %d')} ({person['days_until']} days)"
        with st.expander(label):
            send_text_box(person["name"], person["phone_numbers"], key_prefix=f"bday_{person['id']}")

# --- Tab 2: Follow-up Queue -----------------------------------------------
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

    if not my_cards:
        st.info("Nothing assigned to you right now -- nice and clear!")

    for card in my_cards:
        due_bit = f" — due {card['due_at'][:10]}" if card["due_at"] else ""
        overdue_bit = " ⚠️ OVERDUE" if card["overdue"] else ""
        label = f"{card['person_name']} — {card['workflow_name']} ({card['stage']}){due_bit}{overdue_bit}"
        with st.expander(label):
            try:
                phone_numbers = get_person_phone_numbers(card["person_id"]) if card["person_id"] else []
            except requests.exceptions.RequestException:
                phone_numbers = []
            send_text_box(card["person_name"], phone_numbers, key_prefix=f"followup_{card['card_id']}")

# --- Tab 3: Drifting Regulars ----------------------------------------------
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

    if not drifting_people:
        st.info("No one looks like they're drifting right now.")

    for person in drifting_people:
        label = (
            f"{person['name']} — last seen {person['last_seen'].strftime('%b %d')} "
            f"({person['days_since']} days ago)"
        )
        with st.expander(label):
            st.caption(f"Checked in {person['check_in_count']} times in the last {DRIFT_LOOKBACK_DAYS} days.")
            try:
                phone_numbers = get_person_phone_numbers(person["person_id"])
            except requests.exceptions.RequestException:
                phone_numbers = []
            send_text_box(person["name"], phone_numbers, key_prefix=f"drift_{person['person_id']}")

# --- Tab 4: Find a Person -----------------------------------------------
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

        if not results:
            st.info("No matches found.")

        for person in results:
            with st.expander(person["name"]):
                if person["emails"]:
                    st.caption("Email: " + ", ".join(person["emails"]))
                send_text_box(person["name"], person["phone_numbers"], key_prefix=f"find_{person['id']}")

# --- Tab 5: Texting Inbox -------------------------------------------------
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
# SECTION 6: HOOKS FOR FUTURE PHASES (not built yet)
# ------------------------------------------------------------------
# Phase 4 - optional modules:
#   - New & returning guests (recent first-time check-ins / new people)
#   - Connection gaps (people not in any Group)
#   - "My serving schedule" (upcoming Services plans the owner is on)
#
# See COWORK-PROJECT-BRIEF.md, Section 7, for the full task roadmap.
