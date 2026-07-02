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

# >>> TWEAK ME: how many times showing up within that window counts as
# "regular attendance" -- counts BOTH Check-Ins (worship services,
# kids/students check-in) and Group meeting attendance combined, since
# many churches only check in kids/students and Groups attendance is
# often the only record of an adult actually being there.
DRIFT_MIN_ACTIVITY = 3

# >>> TWEAK ME: if a regular hasn't shown up (by either measure above)
# for this many days, flag them as drifting
DRIFT_THRESHOLD_DAYS = 21

# >>> TWEAK ME: how many days back counts as a "new" profile or first-time guest
NEW_GUEST_LOOKBACK_DAYS = 14

# >>> TWEAK ME: how many "not in a Group" people to show at once (this list
# can be long at a bigger church, so we show a batch at a time instead of
# everyone -- there's a button to see more).
CONNECTION_GAPS_PAGE_SIZE = 25

# >>> TWEAK ME: how many days ahead counts as "this week's" serving
# schedule on the Serving Teams tab
SERVING_LOOKAHEAD_DAYS = 7

# The four ministry age groups people get sorted into (see age_category()
# in Section 2 for exactly how). Order matters here -- it's the order
# shown in every "Age group" dropdown.
AGE_CATEGORIES = ["Preschool", "Children", "Youth", "Adults"]

# >>> TWEAK ME: only people whose Planning Center "Membership" field
# matches one of these (case-insensitive) count as a "member" -- the
# Birthdays and Anniversaries tabs only text people who match. If your
# church uses different wording (e.g. "Full Member", "Covenant Member"),
# add it to this list. See is_member() in Section 2 for more detail.
MEMBER_STATUSES = ["Member"]

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

    /* Buttons -- rounded pill shape, green fill. This also styles the
    two-row section navigation buttons in Section 5 (they're plain
    st.button() widgets, just like "Refresh birthdays" or "Send text").
    Streamlit's own button styles can load after ours, so !important
    makes sure the green pill look always wins. */
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

    /* The currently open section's nav button (a "primary" button --
    every other button on the page is "secondary" and unaffected by this
    rule) gets a white ring so it's obvious which section you're on. */
    div[data-testid="stButton"] button[kind="primary"] {{
        box-shadow: 0 0 0 2px #FFFFFF inset !important;
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

# Used for kids in 5th grade or below (Preschool and Children age groups --
# see age_category() in Section 2), where it's worked out which birthday
# it is (their "age_ordinal") and it's nice to call that out by name.
KID_BIRTHDAY_MESSAGES = [
    "Happy {age_ordinal} birthday, {first_name}! So glad we get to celebrate you today. — {pastor_name}",
    "Hey {first_name}, happy {age_ordinal} birthday! Praying you have a fantastic day. — {pastor_name}",
    "{first_name}, happy {age_ordinal} birthday! Hope it's full of fun and cake. — {pastor_name}",
    "Happy {age_ordinal} birthday, {first_name}! So thankful for you. — {pastor_name}",
    "Hey {first_name} — happy {age_ordinal} birthday! Hope you have the best day. — {pastor_name}",
    "{first_name}, happy {age_ordinal} birthday! Praying this is a great year for you. — {pastor_name}",
    "Happy {age_ordinal} birthday, {first_name}! Excited to celebrate you today. — {pastor_name}",
    "Hey {first_name}, happy {age_ordinal} birthday! Hope today is extra special. — {pastor_name}",
]

# Used for kids in 5th grade or below when we text a parent/guardian
# *instead of* the child directly (see get_parent_contacts() in Section 2)
# -- addressed to the parent, asking them to pass the wish along.
PARENT_RELAY_BIRTHDAY_MESSAGES = [
    "Hi {parent_first_name}! Just a heads up that {child_first_name} turns {age_ordinal} today -- would you mind passing along a birthday wish from us? — {pastor_name}",
    "Hey {parent_first_name}, happy birthday to {child_first_name}! Mind sharing a birthday hug from us today? — {pastor_name}",
    "Hi {parent_first_name}! We're celebrating {child_first_name} turning {age_ordinal} today -- feel free to pass along our excitement! — {pastor_name}",
    "Hey {parent_first_name}, it's {child_first_name}'s birthday today! Would you mind letting them know we're thinking of them? — {pastor_name}",
    "Hi {parent_first_name}! Happy {age_ordinal} birthday to {child_first_name} -- please give them a hug from us. — {pastor_name}",
    "Hey {parent_first_name}, just wanted you to know we're celebrating {child_first_name}'s birthday today -- mind passing that along? — {pastor_name}",
    "Hi {parent_first_name}! {child_first_name} turns {age_ordinal} today -- would love for them to know we're celebrating them. — {pastor_name}",
    "Hey {parent_first_name}, happy birthday to {child_first_name} today! Please tell them we're so thankful for them. — {pastor_name}",
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

# Used on the Serving Teams tab -- a personal thank-you to anyone
# scheduled to serve this week, in any capacity.
SERVING_THANK_YOU_MESSAGES = [
    "Hi {first_name}! Just wanted to say thank you for serving this week -- your investment in this church doesn't go unnoticed. — {pastor_name}",
    "Hey {first_name}, thank you for showing up and serving again this week! It matters more than you know. — {pastor_name}",
    "Hi {first_name}! Grateful for your heart to serve this week. Thank you for investing in this church family. — {pastor_name}",
    "Hey {first_name}, just wanted you to know I see you serving and I'm thankful for it. Thank you! — {pastor_name}",
    "Hi {first_name}! Thanks for serving this week -- your faithfulness is a gift to this church. — {pastor_name}",
    "Hey {first_name}, thank you for saying yes to serve again this week. It really does matter. — {pastor_name}",
    "Hi {first_name}! Wanted to take a second to say thank you for serving this week. Grateful for you. — {pastor_name}",
    "Hey {first_name}, thank you for investing your time to serve this week -- it doesn't go unnoticed. — {pastor_name}",
]

# Used on the New & Returning Guests tab -- a longer, warmer personal
# welcome (these run a few sentences, not just a one-liner) for anyone
# who's new to the church or just showed up again after a while.
GUEST_WELCOME_MESSAGES = [
    "Hi {first_name}! I just wanted to reach out personally and say how glad I am you came to {church_name} recently. I hope you felt welcome and at home while you were with us. If you ever have questions about our church or want help finding a group to plug into, just reply to this text -- I'd love to help. — {pastor_name}",
    "Hey {first_name}, thank you so much for visiting {church_name}! It means a lot to us that you took the time to join us, and I hope it was a meaningful experience. I'd love to hear how you're doing or answer any questions you might have -- feel free to text me back anytime. — {pastor_name}",
    "Hi {first_name}! I wanted to personally welcome you to {church_name}. Whether it was your first time or you're checking us out again, I'm really glad you're here. If there's anything I can do to help you get connected or feel more at home, just let me know. — {pastor_name}",
    "Hey {first_name}, thanks for stopping by {church_name} recently! I hope you left feeling encouraged and welcomed. We'd love to help you take a next step, whether that's a small group, a coffee together, or just answering questions -- reply anytime. — {pastor_name}",
    "Hi {first_name}! So glad you joined us at {church_name}. I know visiting a new church can feel like a big step, and I just wanted you to know we're glad you took it. If you want to talk or have questions about getting connected, I'm just a text away. — {pastor_name}",
    "Hey {first_name}, I wanted to personally thank you for being with us at {church_name}. I hope you felt the warmth of this church family. If you're looking for ways to get more involved or just want to chat, don't hesitate to reach out. — {pastor_name}",
    "Hi {first_name}! It was great having you at {church_name} recently. I hope you found it to be a place worth coming back to. If you have any questions or want help finding your next step here, I'd love to connect -- just reply whenever works for you. — {pastor_name}",
    "Hey {first_name}, thanks for worshiping with us at {church_name}! I hope you felt right at home. If there's ever anything I can do for you -- prayer, questions, or just getting plugged in -- please don't hesitate to reach out. — {pastor_name}",
]

# Used on the Connection Gaps tab -- a longer, personal invitation (a
# few sentences, not just a one-liner) to anyone not currently in a
# small group, encouraging them toward community without any pressure.
CONNECTION_GAP_MESSAGES = [
    "Hi {first_name}! I noticed you're not currently in one of our small groups, and I wanted to personally reach out. Being part of a group is one of the best ways to build real relationships and grow here at {church_name}. I'd love to help you find one that fits -- just let me know what you're looking for. — {pastor_name}",
    "Hey {first_name}, I wanted to check in and see if you'd ever thought about joining a small group at {church_name}. It's such a great way to get to know people and feel more connected. If you're interested, I'd be happy to point you toward a group that might be a good fit. — {pastor_name}",
    "Hi {first_name}! I care about you feeling connected here at {church_name}, and I noticed you're not in a group yet. There's no pressure at all, but if you'd ever like help finding one, I'm happy to walk you through some options. — {pastor_name}",
    "Hey {first_name}, just wanted to reach out personally. Groups are where a lot of the best relationships at {church_name} get built, and I'd love to help you get plugged into one if you're interested. Let me know and I can point you in the right direction. — {pastor_name}",
    "Hi {first_name}! I hope you're doing well. I wanted to personally invite you to consider joining a small group here at {church_name} -- it's a great way to grow and build community. Happy to help you find the right one whenever you're ready. — {pastor_name}",
    "Hey {first_name}, I noticed you haven't found a group yet at {church_name}, and I just wanted to reach out. Groups are one of the best ways to feel connected here, and I'd love to help you find a good fit -- no pressure, just an open door. — {pastor_name}",
    "Hi {first_name}! I wanted to personally check in -- have you ever thought about joining a small group at {church_name}? It really is where a lot of life change happens. I'd be glad to help you find one whenever you're ready. — {pastor_name}",
    "Hey {first_name}, I care about you finding real community here at {church_name}, and I noticed you're not currently in a group. If you'd ever like help finding one that fits your schedule or interests, just let me know -- I'd love to help. — {pastor_name}",
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
    """Build a ready-to-send, personalized birthday text for one person.

    For kids in 5th grade or below (Preschool/Children -- see
    age_category() in Section 2), this calls out which birthday it is
    ("Happy 7th birthday!") using the age they're turning, which
    upcoming_birthdays() works out from their birthdate. Everyone else
    gets one of the general BIRTHDAY_MESSAGES instead."""
    first_name = person["name"].split()[0] if person.get("name") else "there"
    age_turning = person.get("age_turning")
    if age_turning and age_category(person) in ("Preschool", "Children"):
        template = _pick_message(KID_BIRTHDAY_MESSAGES, person["id"] + "_bday")
        return template.format(
            first_name=first_name, pastor_name=PASTOR_NAME, age_ordinal=_ordinal(age_turning)
        )
    template = _pick_message(BIRTHDAY_MESSAGES, person["id"] + "_bday")
    return template.format(first_name=first_name, pastor_name=PASTOR_NAME)


def parent_birthday_message(child, parent):
    """Build a ready-to-send text *to a parent/guardian*, asking them to
    pass a birthday wish along to their child -- used instead of
    birthday_message() when texting the child directly isn't the plan
    (see get_parent_contacts() in Section 2)."""
    child_first_name = child["name"].split()[0] if child.get("name") else "your child"
    parent_first_name = parent["name"].split()[0] if parent.get("name") else "there"
    template = _pick_message(
        PARENT_RELAY_BIRTHDAY_MESSAGES, child["id"] + "_" + parent["person_id"] + "_bdayrelay"
    )
    return template.format(
        parent_first_name=parent_first_name,
        child_first_name=child_first_name,
        age_ordinal=_ordinal(child.get("age_turning") or 0),
        pastor_name=PASTOR_NAME,
    )


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


def serving_thank_you_message(person):
    """Build a ready-to-send, personal thank-you text for one person
    scheduled to serve this week (see get_upcoming_serving_teams() in
    Section 2)."""
    first_name = person["name"].split()[0] if person.get("name") else "there"
    template = _pick_message(SERVING_THANK_YOU_MESSAGES, person["person_id"] + "_serving")
    return template.format(first_name=first_name, pastor_name=PASTOR_NAME)


def guest_welcome_message(person):
    """Build a ready-to-send, personal welcome text (a few sentences,
    not just a one-liner) for a new profile or first-time guest -- works
    with either shape of person dict, since 'new profiles' use an 'id'
    key and 'first-time check-ins' use a 'person_id' key."""
    first_name = person["name"].split()[0] if person.get("name") else "there"
    seed_id = person.get("id") or person.get("person_id") or first_name
    template = _pick_message(GUEST_WELCOME_MESSAGES, str(seed_id) + "_guest")
    return template.format(first_name=first_name, pastor_name=PASTOR_NAME, church_name=CHURCH_NAME)


def connection_gap_message(person):
    """Build a ready-to-send, personal invitation (a few sentences, not
    just a one-liner) for someone not currently in a small group -- see
    get_people_not_in_a_group() in Section 2."""
    first_name = person["name"].split()[0] if person.get("name") else "there"
    template = _pick_message(CONNECTION_GAP_MESSAGES, person["id"] + "_gap")
    return template.format(first_name=first_name, pastor_name=PASTOR_NAME, church_name=CHURCH_NAME)


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
            "membership": person["attributes"].get("membership"),
            "phone_numbers": [p for p in phone_numbers if p],
            "emails": [e for e in emails if e],
        })
    return people


def _belongs_to(included_item, person_id):
    rel = (included_item.get("relationships") or {}).get("person", {}).get("data") or {}
    return rel.get("id") == person_id


def is_member(person):
    """True if this person's Planning Center 'Membership' field matches
    one of the MEMBER_STATUSES settings below (case-insensitive) -- used
    so the Birthdays and Anniversaries tabs only text actual members,
    not visitors, regular attendees, or other guests.

    # >>> TWEAK ME: 'Membership' in Planning Center is a free-text field
    # each church sets up itself (Account -> People -> Membership, or on
    # a person's own profile page). If nobody shows up on the Birthdays
    # or Anniversaries tab when you expect people to, check the exact
    # wording your church uses there and update MEMBER_STATUSES to match.
    """
    membership = (person.get("membership") or "").strip().lower()
    return membership in {status.strip().lower() for status in MEMBER_STATUSES}


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
            person_copy["age_turning"] = next_bday.year - bday.year
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
    """Look up one person's name, phone numbers, grade, and child flag by
    their Planning Center ID -- used by tabs that only get a person's
    ID (not their full contact info) from another endpoint, such as
    Workflow cards, Check-Ins, or Services team members, so they can
    still offer texting, age-group filtering, and a correct name."""
    data = pco_get(f"/people/v2/people/{person_id}", params={"include": "phone_numbers"})
    attrs = data.get("data", {}).get("attributes", {})
    included = data.get("included", [])
    phone_numbers = [
        item["attributes"].get("number", "")
        for item in included
        if item.get("type") == "PhoneNumber" and item["attributes"].get("number")
    ]
    return {
        "name": attrs.get("name"),
        "phone_numbers": phone_numbers,
        "grade": attrs.get("grade"),
        "child": attrs.get("child", False),
    }


def get_parent_contacts(child_person_id):
    """Find the adult(s) in a child's Planning Center Household -- their
    likely parent(s) or guardian(s) -- along with a phone number for each,
    so a birthday note for a young child can go to an adult instead of
    straight to the child.

    This uses Planning Center's Household feature rather than trying to
    guess from a relationship label, so it works no matter how a
    household's relationships are labeled: every *other* person in the
    child's household(s) who counts as an Adult (see age_category() above)
    is treated as a parent/guardian. Households with no other adults on
    file (or no household at all) simply return an empty list -- the
    calling code falls back to texting the child directly in that case.
    """
    households_data = pco_get(f"/people/v2/people/{child_person_id}/households")
    household_ids = [h["id"] for h in households_data.get("data", [])]

    adults_by_id = {}  # person_id -> {"person_id", "name"} (de-duped across households)
    for household_id in household_ids:
        memberships_data = pco_get(
            f"/people/v2/households/{household_id}/household_memberships",
            params={"include": "person"},
        )
        included_people = {
            item["id"]: item
            for item in memberships_data.get("included", [])
            if item.get("type") == "Person"
        }
        for membership in memberships_data.get("data", []):
            person_ref = (membership.get("relationships", {}).get("person") or {}).get("data") or {}
            member_id = person_ref.get("id")
            if not member_id or member_id == child_person_id:
                continue  # skip the child themselves

            member_attrs = included_people.get(member_id, {}).get("attributes", {})
            member_age_info = {"grade": member_attrs.get("grade"), "child": member_attrs.get("child", False)}
            if age_category(member_age_info) != "Adults":
                continue  # skip siblings/other kids in the household

            adults_by_id[member_id] = {
                "person_id": member_id,
                "name": member_attrs.get("name", "(unknown)"),
            }

    # Household memberships don't include phone numbers directly, so look
    # each adult up once here (a small, one-time cost per birthday card).
    parents = []
    for adult in adults_by_id.values():
        try:
            details = get_person_details(adult["person_id"])
        except requests.exceptions.RequestException:
            details = {"phone_numbers": []}
        adult["phone_numbers"] = details.get("phone_numbers", [])
        parents.append(adult)
    return parents


@st.cache_data(ttl=300)  # remembers the result for 5 minutes so we don't hammer the API
def _cached_parent_contacts(child_person_id):
    return get_parent_contacts(child_person_id)


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


def _record_activity(people_seen, person_id, name, activity_date):
    """Add one 'this person was here' data point into the shared
    people_seen dict used by get_drifting_regulars() -- whether that's a
    Check-In or a Group meeting they were marked present at -- bumping
    their activity count and pushing their last-seen date forward if
    this one is more recent than what we already had for them."""
    record = people_seen.setdefault(
        person_id, {"name": name or "(unknown)", "count": 0, "last_seen": activity_date}
    )
    record["count"] += 1
    if activity_date > record["last_seen"]:
        record["last_seen"] = activity_date
    if record["name"] == "(unknown)" and name and name != "(unknown)":
        record["name"] = name


def _accumulate_check_in_activity(people_seen, cutoff):
    """Add every Check-In (worship services, kids/students check-in,
    events -- anything using PCO Check-Ins) since `cutoff` into the
    shared people_seen dict."""
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
            _record_activity(people_seen, person_id, name, created_date)

        if reached_cutoff:
            break

        next_link = (data.get("links") or {}).get("next")
        if not next_link:
            break
        next_url = next_link


def _accumulate_group_attendance(people_seen, cutoff):
    """Add small-group meeting attendance (Planning Center Groups) since
    `cutoff` into the shared people_seen dict, alongside Check-Ins.

    Many churches only use Check-Ins for kids and students (for
    security/pickup), not adults in the main service -- so for a lot of
    adults, a small group's own attendance record is the *only* place
    Planning Center has any sign they were actually there. Combining
    both sources gives a much more complete "drifting" picture across
    every age group, not just kids.

    # >>> TWEAK ME: if your church's Groups don't take attendance (or
    # only some of them do), this will simply add nothing for those
    # groups -- no attendance records means no activity to count. If the
    # Drifting Regulars list looks off, double check with your Groups
    # leaders whether (and how) they're marking attendance each week.
    """
    next_url = None
    params = {"where[archive_status]": "not_archived", "per_page": 100}

    while True:
        if next_url:
            groups_data = _pco_request(next_url)
        else:
            groups_data = pco_get("/groups/v2/groups", params=params)

        for group in groups_data.get("data", []):
            _accumulate_one_groups_events(people_seen, group["id"], cutoff)
            time.sleep(0.1)  # small pause so a church with many groups doesn't trip PCO's rate limit

        next_link = (groups_data.get("links") or {}).get("next")
        if not next_link:
            break
        next_url = next_link


def _accumulate_one_groups_events(people_seen, group_id, cutoff):
    """Page through one Group's past meetings ('events'), newest first,
    stopping once we reach a meeting older than `cutoff` -- same
    early-exit trick used for Check-Ins above."""
    next_url = None
    params = {"order": "-starts_at", "per_page": 100}
    today = datetime.date.today()

    while True:
        if next_url:
            events_data = _pco_request(next_url)
        else:
            events_data = pco_get(f"/groups/v2/groups/{group_id}/events", params=params)

        reached_cutoff = False
        for event in events_data.get("data", []):
            starts_at = event["attributes"].get("starts_at") or ""
            try:
                event_date = datetime.datetime.strptime(starts_at[:10], "%Y-%m-%d").date()
            except ValueError:
                continue

            if event_date < cutoff:
                reached_cutoff = True
                break
            if event_date > today:
                continue  # a future meeting hasn't happened yet -- nothing to count

            _accumulate_one_event_attendance(people_seen, event["id"], event_date)
            time.sleep(0.05)  # a small pause -- some groups meet weekly for months

        if reached_cutoff:
            break

        next_link = (events_data.get("links") or {}).get("next")
        if not next_link:
            break
        next_url = next_link


def _accumulate_one_event_attendance(people_seen, event_id, event_date):
    """Add everyone marked 'attended' at one Group meeting into the
    shared people_seen dict."""
    next_url = None
    params = {"include": "person", "per_page": 100}

    while True:
        if next_url:
            attendance_data = _pco_request(next_url)
        else:
            attendance_data = pco_get(f"/groups/v2/events/{event_id}/attendances", params=params)

        included_people = {
            item["id"]: item for item in attendance_data.get("included", [])
            if item.get("type") == "Person"
        }

        for record in attendance_data.get("data", []):
            if not record["attributes"].get("attended"):
                continue  # marked absent for this meeting -- doesn't count as activity

            person_ref = (record.get("relationships", {}).get("person") or {}).get("data")
            if not person_ref:
                continue

            person_id = person_ref["id"]
            person_attrs = included_people.get(person_id, {}).get("attributes", {})
            name = person_attrs.get("name") or "(unknown)"
            _record_activity(people_seen, person_id, name, event_date)

        next_link = (attendance_data.get("links") or {}).get("next")
        if not next_link:
            break
        next_url = next_link


def get_drifting_regulars():
    """Look at recent attendance to find people who used to come
    consistently but have gone quiet lately -- so nobody slips away
    unnoticed. Looks at BOTH Planning Center Check-Ins (worship
    services, kids/students check-in) and Groups meeting attendance
    (small groups), since many churches only check in kids/students --
    Groups attendance is often the only record of an adult regularly
    showing up at all.

    How "drifting" is decided (see the TWEAK ME settings up top):
      1. Look back DRIFT_LOOKBACK_DAYS days of activity, church-wide.
      2. Anyone with DRIFT_MIN_ACTIVITY or more check-ins/meetings
         attended (combined) in that window counts as a "regular".
      3. If a regular's most recent activity was more than
         DRIFT_THRESHOLD_DAYS days ago, they're flagged as drifting.
    """
    cutoff = datetime.date.today() - datetime.timedelta(days=DRIFT_LOOKBACK_DAYS)
    people_seen = {}  # person_id -> {"name", "count", "last_seen"}

    _accumulate_check_in_activity(people_seen, cutoff)
    _accumulate_group_attendance(people_seen, cutoff)

    today = datetime.date.today()
    drifting = []
    for person_id, info in people_seen.items():
        if info["count"] < DRIFT_MIN_ACTIVITY:
            continue  # wasn't attending regularly to begin with
        days_since = (today - info["last_seen"]).days
        if days_since >= DRIFT_THRESHOLD_DAYS:
            drifting.append({
                "person_id": person_id,
                "name": info["name"],
                "last_seen": info["last_seen"],
                "days_since": days_since,
                "activity_count": info["count"],
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


SERVING_STATUS_LABELS = {"C": "Confirmed", "U": "Unconfirmed", "D": "Declined"}


def _list_all_service_types():
    """Every Planning Center Services 'service type' -- these are the
    church's different serving teams/ministries (e.g. Sunday Worship,
    Kids, Production, Youth), each with its own list of upcoming Plans."""
    service_types = []
    next_url = None
    params = {"per_page": 100}

    while True:
        if next_url:
            data = _pco_request(next_url)
        else:
            data = pco_get("/services/v2/service_types", params=params)

        for item in data.get("data", []):
            service_types.append({"id": item["id"], "name": item["attributes"].get("name") or "(a service)"})

        next_link = (data.get("links") or {}).get("next")
        if not next_link:
            break
        next_url = next_link

    return service_types


def _list_upcoming_plans(service_type_id, cutoff_date):
    """Upcoming Plans (individual dates -- e.g. this Sunday's service)
    for one service type, stopping once we're past `cutoff_date`."""
    today = datetime.date.today()
    plans = []
    next_url = None
    params = {"filter": "future", "order": "sort_date", "per_page": 100}

    while True:
        if next_url:
            data = _pco_request(next_url)
        else:
            data = pco_get(f"/services/v2/service_types/{service_type_id}/plans", params=params)

        for item in data.get("data", []):
            attrs = item["attributes"]
            sort_date = attrs.get("sort_date") or ""
            try:
                plan_date = datetime.datetime.strptime(sort_date[:10], "%Y-%m-%d").date()
            except ValueError:
                continue

            # Plans come back soonest-first, so once we're past our
            # lookahead window we can stop paging entirely.
            if plan_date > cutoff_date:
                return plans
            if plan_date < today:
                continue  # shouldn't happen with filter=future, but just in case

            plans.append({
                "id": item["id"],
                "dates": attrs.get("dates") or attrs.get("short_dates"),
            })

        next_link = (data.get("links") or {}).get("next")
        if not next_link:
            break
        next_url = next_link

    return plans


def _list_plan_team_members(service_type_id, plan_id):
    """Everyone scheduled to serve (in any team/position) for one Plan,
    confirmed or not -- this is where the actual list of names lives."""
    members = []
    next_url = None
    params = {"include": "person", "per_page": 100}

    while True:
        if next_url:
            data = _pco_request(next_url)
        else:
            data = pco_get(
                f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/team_members",
                params=params,
            )

        included_people = {
            item["id"]: item for item in data.get("included", []) if item.get("type") == "Person"
        }

        for item in data.get("data", []):
            attrs = item["attributes"]
            person_ref = (item.get("relationships", {}).get("person") or {}).get("data")
            if not person_ref:
                continue

            person_attrs = included_people.get(person_ref["id"], {}).get("attributes", {})
            members.append({
                "person_id": person_ref["id"],
                "name": person_attrs.get("name") or "(unknown)",
                "team_position_name": attrs.get("team_position_name") or "Serving",
                "status": attrs.get("status"),
            })

        next_link = (data.get("links") or {}).get("next")
        if not next_link:
            break
        next_url = next_link

    return members


def get_upcoming_serving_teams(days_ahead=SERVING_LOOKAHEAD_DAYS):
    """Find everyone scheduled to serve in any capacity, on any team, in
    the next `days_ahead` days -- across the whole church, not just
    whoever owns these API keys. Each person's card lists every role
    they're serving in this window (some people serve more than once).

    Declined signups are left out -- someone who said no isn't actually
    serving. Confirmed and not-yet-confirmed signups are both included,
    with unconfirmed ones labeled so you know at a glance.
    """
    cutoff_date = datetime.date.today() + datetime.timedelta(days=days_ahead)
    people = {}  # person_id -> {"person_id", "name", "roles": [str, ...]}

    for service_type in _list_all_service_types():
        for plan in _list_upcoming_plans(service_type["id"], cutoff_date):
            for member in _list_plan_team_members(service_type["id"], plan["id"]):
                if member["status"] == "D":
                    continue  # declined -- not actually serving

                status_label = SERVING_STATUS_LABELS.get(member["status"])
                status_bit = f" ({status_label})" if status_label == "Unconfirmed" else ""
                dates_bit = f" — {plan['dates']}" if plan.get("dates") else ""
                role = f"{member['team_position_name']} · {service_type['name']}{dates_bit}{status_bit}"

                entry = people.setdefault(
                    member["person_id"], {"person_id": member["person_id"], "name": member["name"], "roles": []}
                )
                entry["roles"].append(role)

    # team_members' included Person data doesn't reliably carry a usable
    # "name" in every Planning Center account, so look each person up
    # once here -- this also fetches their phone number (a small,
    # one-time cost per serving week either way) and gives us a name we
    # can actually trust.
    results = []
    for entry in people.values():
        try:
            details = get_person_details(entry["person_id"])
        except requests.exceptions.RequestException:
            details = {"phone_numbers": []}
        entry["name"] = details.get("name") or entry["name"]
        entry["phone_numbers"] = details.get("phone_numbers", [])
        results.append(entry)

    results.sort(key=lambda p: p["name"].lower())
    return results


@st.cache_data(ttl=600)
def _cached_upcoming_serving_teams():
    return get_upcoming_serving_teams()


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


def age_group_filter(people, key_prefix, categories=None):
    """Show the 'Age group' dropdown and return only the people in
    whichever group was picked. Every person dict passed in needs a
    'grade' and 'child' key (see age_category() in Section 2) for this
    to sort correctly.

    Pass `categories` to limit which groups show up in the dropdown
    (e.g. ["Youth", "Adults"] on a tab that shouldn't offer kids as a
    choice at all) -- defaults to all four groups."""
    categories = categories or AGE_CATEGORIES
    choice = st.selectbox(
        "Age group", ["All ages"] + categories, key=f"{key_prefix}_age_filter"
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

# Navigation -- green pill buttons, two rows, instead of Streamlit's
# default single-row scrolling tab strip (nothing gets hidden off to the
# side, and buttons are bigger/easier to tap on an iPad). The currently
# open section stays highlighted with a white ring so it's obvious which
# one you're on.
#
# >>> TWEAK ME: NAV_ITEMS is the master list of sections -- reorder,
# rename, or add/remove entries here (each is a short internal "key" and
# the button label shown on screen). NAV_BUTTONS_PER_ROW controls how
# many buttons fit on the first row before wrapping to a second row.
NAV_ITEMS = [
    ("birthdays", "🎂 Birthdays"),
    ("anniversaries", "💍 Anniversaries"),
    ("followup", "📋 Follow-up Queue"),
    ("drifting", "📉 Drifting Regulars"),
    ("new_guests", "🙌 New & Returning Guests"),
    ("connection_gaps", "🧩 Connection Gaps"),
    ("serving_teams", "🗓️ Serving Teams"),
    ("find_person", "🔍 Find a Person"),
    ("inbox", "💬 Texting Inbox"),
]
NAV_BUTTONS_PER_ROW = 5

if "active_tab" not in st.session_state:
    st.session_state.active_tab = NAV_ITEMS[0][0]

for row_start in range(0, len(NAV_ITEMS), NAV_BUTTONS_PER_ROW):
    row_items = NAV_ITEMS[row_start:row_start + NAV_BUTTONS_PER_ROW]
    nav_columns = st.columns(len(row_items))
    for nav_column, (nav_key, nav_label) in zip(nav_columns, row_items):
        with nav_column:
            is_active = st.session_state.active_tab == nav_key
            if st.button(
                nav_label, key=f"nav_{nav_key}", use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.active_tab = nav_key
                st.rerun()

active_tab = st.session_state.active_tab
st.divider()

# --- Tab 1: Birthdays --------------------------------------------------
if active_tab == "birthdays":
    st.subheader(f"Birthdays in the next {BIRTHDAY_LOOKAHEAD_DAYS} days")
    st.caption("Members only -- see MEMBER_STATUSES in Section 1 to change who counts.")

    if st.button("Refresh birthdays"):
        st.cache_data.clear()

    try:
        with st.spinner("Loading people from Planning Center..."):
            all_people = _cached_all_people()
    except requests.exceptions.RequestException as e:
        st.error(f"Couldn't reach Planning Center: {e}")
        all_people = []

    member_people = [p for p in all_people if is_member(p)]
    birthday_people = upcoming_birthdays(member_people)
    birthday_people = age_group_filter(birthday_people, key_prefix="bday")

    if not birthday_people:
        st.info("No birthdays in the next week.")

    for person in birthday_people:
        label = f"{person['name']} — {person['next_birthday'].strftime('%b %d')} ({person['days_until']} days)"
        with st.expander(label):
            first_name = person["name"].split()[0] if person.get("name") else "them"

            # For kids in 5th grade or below, text a parent/guardian from
            # their Planning Center Household instead of the child --
            # asking them to pass the birthday wish along. If no parent
            # is found on file (or none has a phone number), fall back to
            # texting the child directly, same as everyone else.
            parents = []
            if age_category(person) in ("Preschool", "Children"):
                try:
                    parents = [p for p in _cached_parent_contacts(person["id"]) if p["phone_numbers"]]
                except requests.exceptions.RequestException:
                    parents = []

            if parents:
                st.caption(f"{first_name} is a kid, so this goes to their parent/guardian instead.")
                for parent in parents:
                    st.markdown(f"**To {parent['name']}**")
                    send_text_box(
                        parent["name"], parent["phone_numbers"],
                        key_prefix=f"bday_{person['id']}_parent_{parent['person_id']}",
                        default_message=parent_birthday_message(person, parent),
                    )
            else:
                if age_category(person) in ("Preschool", "Children"):
                    st.caption("No parent/guardian phone number on file -- texting them directly instead.")
                send_text_box(
                    person["name"], person["phone_numbers"], key_prefix=f"bday_{person['id']}",
                    default_message=birthday_message(person),
                )

# --- Tab 2: Anniversaries -------------------------------------------------
if active_tab == "anniversaries":
    st.subheader(f"Anniversaries in the next {ANNIVERSARY_LOOKAHEAD_DAYS} days")
    st.caption("Members only -- see MEMBER_STATUSES in Section 1 to change who counts.")

    if st.button("Refresh anniversaries"):
        st.cache_data.clear()

    try:
        with st.spinner("Loading people from Planning Center..."):
            all_people = _cached_all_people()
    except requests.exceptions.RequestException as e:
        st.error(f"Couldn't reach Planning Center: {e}")
        all_people = []

    member_people = [p for p in all_people if is_member(p)]
    anniversary_people = upcoming_anniversaries(member_people)
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
if active_tab == "followup":
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
if active_tab == "drifting":
    st.subheader("People who may be drifting away")
    st.caption(
        f"People with {DRIFT_MIN_ACTIVITY}+ check-ins or Group meetings attended in the last "
        f"{DRIFT_LOOKBACK_DAYS} days, but none in the last {DRIFT_THRESHOLD_DAYS} days."
    )

    if st.button("Refresh drifting list"):
        st.cache_data.clear()

    try:
        with st.spinner("Looking at recent Check-Ins and Group attendance..."):
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
            st.caption(
                f"Checked in or attended a Group meeting {person['activity_count']} times "
                f"in the last {DRIFT_LOOKBACK_DAYS} days."
            )
            send_text_box(person["name"], person["phone_numbers"], key_prefix=f"drift_{person['person_id']}")

# --- Tab 5: New & Returning Guests ---------------------------------------
if active_tab == "new_guests":
    st.subheader("New & returning guests")
    st.caption(
        f"Planning Center activity from the last {NEW_GUEST_LOOKBACK_DAYS} days. "
        "Youth and older only -- kids are left off this list."
    )

    if st.button("Refresh guests"):
        st.cache_data.clear()

    st.markdown("**New profiles added**")
    try:
        with st.spinner("Checking for new profiles..."):
            new_people = _cached_new_people()
    except requests.exceptions.RequestException as e:
        st.error(f"Couldn't reach Planning Center: {e}")
        new_people = []

    # Kids are handled through their parents elsewhere (see Birthdays),
    # not texted directly as if they were a new guest themselves.
    new_people = [p for p in new_people if age_category(p) not in ("Preschool", "Children")]
    new_people = age_group_filter(new_people, key_prefix="newperson", categories=["Youth", "Adults"])

    if not new_people:
        st.caption("No new profiles recently.")
    for person in new_people:
        with st.expander(person["name"]):
            send_text_box(
                person["name"], person["phone_numbers"], key_prefix=f"newperson_{person['id']}",
                default_message=guest_welcome_message(person),
            )

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

    # Kids are handled through their parents elsewhere (see Birthdays),
    # not texted directly as if they were a new guest themselves.
    enriched_first_timers = [
        g for g in enriched_first_timers if age_category(g) not in ("Preschool", "Children")
    ]
    first_timers = age_group_filter(enriched_first_timers, key_prefix="firsttime", categories=["Youth", "Adults"])

    if not first_timers:
        st.caption("No first-time check-ins recently.")
    for guest in first_timers:
        label = f"{guest['name']} — checked in {guest['checked_in_on'].strftime('%b %d')}"
        with st.expander(label):
            send_text_box(
                guest["name"], guest["phone_numbers"], key_prefix=f"firsttime_{guest['person_id']}",
                default_message=guest_welcome_message(guest),
            )

# --- Tab 6: Connection Gaps ------------------------------------------------
if active_tab == "connection_gaps":
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
            send_text_box(
                person["name"], person["phone_numbers"], key_prefix=f"gap_{person['id']}",
                default_message=connection_gap_message(person),
            )

    if shown_count < len(ungrouped_people):
        st.caption(f"Showing {min(shown_count, len(ungrouped_people))} of {len(ungrouped_people)}.")
        if st.button("Show more"):
            st.session_state.connection_gaps_shown += CONNECTION_GAPS_PAGE_SIZE
            st.rerun()

# --- Tab 7: Serving Teams ---------------------------------------------
if active_tab == "serving_teams":
    st.subheader(f"Everyone serving in the next {SERVING_LOOKAHEAD_DAYS} days")
    st.caption(
        "Every person scheduled to serve in any capacity, on any team, church-wide -- "
        "with a personal thank-you text ready to send."
    )

    if st.button("Refresh serving teams"):
        st.cache_data.clear()

    try:
        with st.spinner("Loading serving schedules from Planning Center Services..."):
            serving_people = _cached_upcoming_serving_teams()
    except requests.exceptions.RequestException as e:
        st.error(f"Couldn't reach Planning Center Services: {e}")
        serving_people = []

    if not serving_people:
        st.info("Nobody is scheduled to serve in the next week.")

    for person in serving_people:
        label = f"{person['name']} — {', '.join(person['roles'])}"
        with st.expander(label):
            send_text_box(
                person["name"], person["phone_numbers"], key_prefix=f"serving_{person['person_id']}",
                default_message=serving_thank_you_message(person),
            )

# --- Tab 8: Find a Person -----------------------------------------------
if active_tab == "find_person":
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
if active_tab == "inbox":
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
#   Phase 4 - New & Returning Guests, Connection Gaps, Serving Teams
#
# Nothing left on the original roadmap -- future ideas can go here.
