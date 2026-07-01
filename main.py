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
  5. The actual page    -- all nine tabs

Look for "# >>> TWEAK ME" comments -- those are safe, simple
settings you can change without breaking anything else.
============================================================
"""

import os
import time
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

    if not birthday_people:
        st.info("No birthdays in the next week.")

    for person in birthday_people:
        label = f"{person['name']} — {person['next_birthday'].strftime('%b %d')} ({person['days_until']} days)"
        with st.expander(label):
            send_text_box(person["name"], person["phone_numbers"], key_prefix=f"bday_{person['id']}")

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

    if not anniversary_people:
        st.info("No anniversaries in the next week.")

    for person in anniversary_people:
        years_bit = f", {person['years_married']} years" if person["years_married"] > 0 else ""
        label = (
            f"{person['name']} — {person['next_anniversary'].strftime('%b %d')} "
            f"({person['days_until']} days{years_bit})"
        )
        with st.expander(label):
            send_text_box(person["name"], person["phone_numbers"], key_prefix=f"anniv_{person['id']}")

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

    if not first_timers:
        st.caption("No first-time check-ins recently.")
    for guest in first_timers:
        label = f"{guest['name']} — checked in {guest['checked_in_on'].strftime('%b %d')}"
        with st.expander(label):
            try:
                phone_numbers = get_person_phone_numbers(guest["person_id"])
            except requests.exceptions.RequestException:
                phone_numbers = []
            send_text_box(guest["name"], phone_numbers, key_prefix=f"firsttime_{guest['person_id']}")

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
