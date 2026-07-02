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
  5. The actual page    -- all ten tabs

Look for "# >>> TWEAK ME" comments -- those are safe, simple
settings you can change without breaking anything else.
============================================================
"""

import os
import re
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

# >>> TWEAK ME: someone counts as a "new giver" if their very first
# recorded gift landed within this many days -- see get_new_givers() in
# Section 2. Needs "giving-view" permission on the Planning Center token
# (see Setup Guide, Step 1) or this tab will show a permission error.
NEW_GIVER_LOOKBACK_DAYS = 30

# >>> TWEAK ME: Connection Gaps tries to figure out who a class is for
# straight from its name -- e.g. "Men's Classes 30-50" or "Couples
# Classes 30-50" -- picking up on gender words (Men/Women/Ladies), age
# ranges (30-50, 65+, Under 18), and marital-status words
# (Couples/Married/Singles). See _parse_class_criteria() in Section 2.
# A person can match more than one class this way -- a married 32-year-
# old man would show up for both examples above.
#
# For any class whose name DOESN'T spell that out (e.g. "Financial
# Peace", or a kids Sunday School class), this setting is the fallback:
# match these to the exact Group Type names you've already set up under
# Groups -> Group Types in Planning Center (case-insensitive), e.g.
# "Adults": ["Adult Groups", "Recovery"]. Leave a category's list empty
# to show every such class for that age instead of narrowing it down.
GROUP_TYPES_BY_AGE_CATEGORY = {
    "Preschool": [],
    "Children": [],
    "Youth": [],
    "Adults": [],
}

# >>> TWEAK ME: for any class where the name-based guessing above won't
# get it right, describe it here instead -- this always wins over the
# automatic guess. Match the "name" key exactly to that Group's name in
# Planning Center. Leave gender/min_age/max_age/marital_status as None
# for anything that's open to everyone. Example:
#   CLASS_CRITERIA_OVERRIDES = {
#       "Financial Peace": {
#           "gender": None, "min_age": None, "max_age": None, "marital_status": None,
#       },
#   }
CLASS_CRITERIA_OVERRIDES = {}

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


# Used on the New Givers tab -- a one-sentence description of what
# giving actually supports, dropped into every message below.
#
# >>> TWEAK ME: this is a generic placeholder. Swap it out for your
# church's actual mission/vision wording whenever you have it ready --
# just keep the {church_name} placeholder if you want that to keep
# filling in automatically.
GIVING_MISSION_SENTENCE = (
    "Every gift to {church_name} helps fund everything from weekly worship "
    "and student ministry to local outreach and missions around the world."
)

# >>> TWEAK ME: a few commonly-taught, church-neutral stewardship
# principles -- one gets randomly-but-consistently sprinkled into each
# new-giver text so it reads like genuine encouragement, not just a
# thank-you note. Swap these out for practices specific to how your
# church actually manages money whenever you're ready (e.g. how you
# budget, build reserves, or avoid debt) -- just keep each one as a
# short, lowercase phrase that finishes the sentence "one thing worth
# remembering: ___."
STEWARDSHIP_TIPS = [
    "giving first, before the rest of the budget gets spent, tends to keep generosity from becoming an afterthought",
    "even a simple, rough budget is one of the most powerful tools for staying free from financial stress",
    "avoiding debt where possible keeps you flexible to give and serve wherever God leads next",
    "building a small emergency reserve helps steady a household through the unexpected",
    "giving consistently, even in small amounts, builds a habit that matters more than the size of any single gift",
    "generosity tends to grow when it's planned ahead of time instead of decided in the moment",
]

# Used on the New Givers tab -- a warm, multi-sentence thank-you for
# someone's first recorded gift (see get_new_givers() in Section 2),
# paired with a bit of encouragement about where the money goes and one
# rotating stewardship tip.
NEW_GIVER_MESSAGES = [
    "Hi {first_name}! I saw that you recently gave to {church_name} for the first time, and I wanted to personally say thank you. {mission_sentence} One thing worth remembering as you keep growing as a giver: {stewardship_tip}. Grateful you're part of this church family. — {pastor_name}",
    "Hey {first_name}, thank you so much for your recent gift to {church_name}! {mission_sentence} I also just want to encourage you with this: {stewardship_tip}. It's an honor to have you giving alongside us. — {pastor_name}",
    "Hi {first_name}! I wanted to reach out and say thank you for giving recently at {church_name} -- it really does matter. {mission_sentence} A simple stewardship reminder as you keep going: {stewardship_tip}. Thankful for your heart to give. — {pastor_name}",
    "Hey {first_name}, thank you for stepping out and giving to {church_name} recently -- it means a lot. {mission_sentence} Here's one thing that's helped a lot of people in our church: {stewardship_tip}. Grateful for you. — {pastor_name}",
    "Hi {first_name}! I noticed your recent gift to {church_name} and wanted to personally thank you for it. {mission_sentence} As you keep building a habit of giving, remember that {stewardship_tip}. So glad you're investing here. — {pastor_name}",
    "Hey {first_name}, thank you for your generosity toward {church_name} recently! {mission_sentence} One encouragement as you keep growing as a giver: {stewardship_tip}. Thankful to have you with us. — {pastor_name}",
    "Hi {first_name}! Your recent gift to {church_name} didn't go unnoticed, and I wanted to say thank you personally. {mission_sentence} A quick stewardship thought worth carrying with you: {stewardship_tip}. Grateful for your generosity. — {pastor_name}",
    "Hey {first_name}, thank you for giving to {church_name} recently -- I wanted you to know it matters. {mission_sentence} Something worth remembering as you keep giving: {stewardship_tip}. So thankful for you. — {pastor_name}",
]


# Used on the Connection Gaps tab -- a personal invite naming one
# specific class/group (see get_class_catalog() in Section 2), instead
# of a generic "join a group somewhere" message.
CLASS_INVITE_MESSAGES = [
    "Hi {first_name}! I think you'd really enjoy {class_name} here at {church_name} -- I wanted to personally invite you to check it out. It's a great way to meet people and grow. Let me know if you have any questions. — {pastor_name}",
    "Hey {first_name}, I thought of you when I was thinking through our classes here, and {class_name} came to mind. I'd love for you to give it a try -- no pressure, just an open invitation. — {pastor_name}",
    "Hi {first_name}! Have you ever thought about joining {class_name} at {church_name}? I think it could be a great fit for you, and I'd love to help you get connected if you're interested. — {pastor_name}",
    "Hey {first_name}, I wanted to personally recommend {class_name} to you. It's a great group here at {church_name}, and I think you'd feel right at home. Let me know if you'd like more info. — {pastor_name}",
    "Hi {first_name}! I think {class_name} might be exactly what you're looking for as far as getting connected here at {church_name}. I'd love for you to check it out whenever you're ready. — {pastor_name}",
    "Hey {first_name}, just wanted to personally point you toward {class_name} -- I think it'd be a great next step for you here at {church_name}. Happy to answer any questions. — {pastor_name}",
]

# Used on the Connection Gaps tab -- a quick heads-up text to a
# class/group leader about a potential new person, since Clearstream
# (the texting platform this dashboard uses) doesn't support one shared
# text thread between two different people. Instead of trying to fake a
# "group text," this sends the leader their own personal note with the
# prospect's name and phone number, so they can follow up directly --
# see get_class_catalog() and the Connection Gaps tab in Section 5.
LEADER_HEADSUP_MESSAGES = [
    "Hi {leader_first_name}! Wanted to give you a heads up -- {prospect_name} might be a great fit for {class_name}, and I already invited them to check it out. Feel free to reach out personally if you'd like! Their number is {prospect_phone}. — {pastor_name}",
    "Hey {leader_first_name}, just a quick note -- I mentioned {class_name} to {prospect_name} and think they could be a great addition. Would you mind reaching out to them personally? Their number is {prospect_phone}. — {pastor_name}",
    "Hi {leader_first_name}! Wanted you to know about a potential new person for {class_name} -- {prospect_name}. I already reached out to invite them, but a personal follow-up from you would go a long way. Number: {prospect_phone}. — {pastor_name}",
    "Hey {leader_first_name}, {prospect_name} came up as someone who might fit really well in {class_name}. I've already sent them an invite, but would love for you to follow up too. Their number is {prospect_phone}. — {pastor_name}",
]


def class_invite_message(person, class_name):
    """Build a ready-to-send, personal invite to one specific class or
    group -- used instead of the general connection_gap_message() when
    a specific recommendation has been picked (see get_class_catalog()
    and recommend_classes_for_person() in Section 2)."""
    first_name = person["name"].split()[0] if person.get("name") else "there"
    template = _pick_message(CLASS_INVITE_MESSAGES, person["id"] + "_class_" + class_name)
    return template.format(
        first_name=first_name, pastor_name=PASTOR_NAME, church_name=CHURCH_NAME, class_name=class_name
    )


def leader_headsup_message(person, class_name, leader):
    """Build a ready-to-send heads-up text for a class/group leader
    about a potential new person for their group -- sent as its own
    separate text (not a shared thread) alongside class_invite_message()
    above."""
    prospect_name = person["name"] if person.get("name") else "someone"
    leader_first_name = leader["name"].split()[0] if leader.get("name") else "there"
    prospect_phone = person["phone_numbers"][0] if person.get("phone_numbers") else "(no number on file)"
    template = _pick_message(LEADER_HEADSUP_MESSAGES, person["id"] + "_" + leader["person_id"] + "_headsup")
    return template.format(
        leader_first_name=leader_first_name, prospect_name=prospect_name,
        prospect_phone=prospect_phone, class_name=class_name, pastor_name=PASTOR_NAME,
    )


# Used on the Connection Gaps tab when a class (like a Couples class)
# matches BOTH people in a married couple at once -- one combined
# heads-up mentioning both names, instead of sending the leader two
# separate texts about the same couple.
LEADER_HEADSUP_COUPLE_MESSAGES = [
    "Hi {leader_first_name}! Wanted to give you a heads up -- {prospect_names} might be a great fit for {class_name}, and I already invited them to check it out together. Feel free to reach out personally if you'd like! Numbers: {prospect_phones}. — {pastor_name}",
    "Hey {leader_first_name}, just a quick note -- I mentioned {class_name} to {prospect_names} and think they could be a great addition as a couple. Would you mind reaching out to them personally? Numbers: {prospect_phones}. — {pastor_name}",
    "Hi {leader_first_name}! Wanted you to know about a potential new couple for {class_name} -- {prospect_names}. I already reached out to invite them, but a personal follow-up from you would go a long way. Numbers: {prospect_phones}. — {pastor_name}",
    "Hey {leader_first_name}, {prospect_names} came up as a couple who might fit really well in {class_name}. I've already sent them both an invite, but would love for you to follow up too. Numbers: {prospect_phones}. — {pastor_name}",
]


def leader_headsup_couple_message(person_a, person_b, class_name, leader):
    """Same idea as leader_headsup_message() above, but for a married
    couple who both match the same class (see get_spouse() in Section 2
    and the Connection Gaps tab in Section 5) -- one heads-up text
    naming both spouses instead of two separate texts about the same
    couple."""
    prospect_names = f"{person_a.get('name', 'someone')} & {person_b.get('name', 'their spouse')}"
    leader_first_name = leader["name"].split()[0] if leader.get("name") else "there"
    phones = [
        p["phone_numbers"][0] for p in (person_a, person_b) if p.get("phone_numbers")
    ]
    prospect_phones = ", ".join(phones) if phones else "(no number on file)"
    template = _pick_message(
        LEADER_HEADSUP_COUPLE_MESSAGES,
        person_a["id"] + "_" + person_b["id"] + "_" + leader["person_id"] + "_headsup_couple",
    )
    return template.format(
        leader_first_name=leader_first_name, prospect_names=prospect_names,
        prospect_phones=prospect_phones, class_name=class_name, pastor_name=PASTOR_NAME,
    )


def new_giver_message(person):
    """Build a ready-to-send, multi-sentence thank-you text for someone
    whose first recorded gift falls inside the lookback window -- see
    get_new_givers() in Section 2. Combines a thank-you, a one-sentence
    reminder of what giving supports, and one rotating stewardship tip
    (both people picked deterministically, same idea as _pick_message()
    below, so the mix stays varied across people but stable for any one
    person across reloads)."""
    first_name = person["name"].split()[0] if person.get("name") else "there"
    mission_sentence = GIVING_MISSION_SENTENCE.format(church_name=CHURCH_NAME)
    stewardship_tip = _pick_message(STEWARDSHIP_TIPS, person["id"] + "_newgiver_tip")
    template = _pick_message(NEW_GIVER_MESSAGES, person["id"] + "_newgiver")
    return template.format(
        first_name=first_name, pastor_name=PASTOR_NAME, church_name=CHURCH_NAME,
        mission_sentence=mission_sentence, stewardship_tip=stewardship_tip,
    )


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


def _debug_raw_person_attributes(name_query):
    """TEMPORARY diagnostic helper -- returns Planning Center's raw,
    unfiltered attributes dict for the first search match, so we can
    see the exact field names/values PCO is actually sending back (used
    to debug why a field like marital_status might not be matching what
    you see in the Planning Center UI). Safe to delete once that's
    sorted out -- see the Find a Person tab in Section 5."""
    data = pco_get("/people/v2/people", params={"where[search_name]": name_query})
    people = data.get("data", [])
    return people[0]["attributes"] if people else None


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
            "gender": person["attributes"].get("gender"),
            "marital_status": person["attributes"].get("marital_status"),
            "age": _calculate_age(person["attributes"].get("birthdate")),
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


def _calculate_age(birthdate_str):
    """Turn a Planning Center birthdate ('YYYY-MM-DD') into a whole
    number of years old today -- used for gender/age/marital-status
    class matching on the Connection Gaps tab (see
    recommend_classes_for_person() below). Returns None if there's no
    birthdate on file, or it's not in the expected format."""
    if not birthdate_str:
        return None
    try:
        birthdate = datetime.datetime.strptime(birthdate_str, "%Y-%m-%d").date()
    except ValueError:
        return None
    today = datetime.date.today()
    had_birthday_this_year = (today.month, today.day) >= (birthdate.month, birthdate.day)
    return today.year - birthdate.year - (0 if had_birthday_this_year else 1)


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


def get_spouse(person_id):
    """Find this person's spouse using Planning Center's Household
    feature -- same approach as get_parent_contacts() above, but looks
    for exactly one OTHER adult in the same household(s) who is also
    marked "Married" instead of looking for a child's guardian.

    Used on the Connection Gaps tab so married people can be grouped
    together with their spouse instead of showing as two disconnected
    rows, and so a couples class can be offered to both at once.

    Returns None if there's no clear single match -- no household on
    file, no other married adult in it, or more than one candidate
    (e.g. a widowed parent also living there) -- better to show
    nothing than guess wrong about who someone's spouse is.

    # >>> This assumes a simple household with one married couple in
    # it. More complex households (multiple couples, a live-in parent,
    # roommates) may not resolve to a spouse even when one exists.
    """
    households_data = pco_get(f"/people/v2/people/{person_id}/households")
    household_ids = [h["id"] for h in households_data.get("data", [])]

    candidates = {}  # person_id -> person dict, de-duped across households
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
            if not member_id or member_id == person_id:
                continue  # skip the person themselves

            member_attrs = included_people.get(member_id, {}).get("attributes", {})
            member_age_info = {"grade": member_attrs.get("grade"), "child": member_attrs.get("child", False)}
            if age_category(member_age_info) != "Adults":
                continue  # skip kids/students in the household

            marital = (member_attrs.get("marital_status") or "").strip().lower()
            if "married" not in marital:
                continue  # skip unmarried adults, e.g. an adult child still at home

            candidates[member_id] = {
                "id": member_id,
                "name": member_attrs.get("name") or "(unknown)",
                "gender": member_attrs.get("gender"),
                "marital_status": member_attrs.get("marital_status"),
                "age": _calculate_age(member_attrs.get("birthdate")),
                "grade": member_attrs.get("grade"),
                "child": member_attrs.get("child", False),
            }

    if len(candidates) != 1:
        return None  # no spouse on file, or too ambiguous to guess which one is the spouse

    spouse = next(iter(candidates.values()))
    try:
        details = get_person_details(spouse["id"])
    except requests.exceptions.RequestException:
        details = {"phone_numbers": []}
    spouse["phone_numbers"] = details.get("phone_numbers", [])
    return spouse


@st.cache_data(ttl=600)  # remembers the result for 10 minutes so we don't hammer the API
def _cached_spouse(person_id):
    return get_spouse(person_id)


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


def _list_all_group_types():
    """Every Planning Center Group Type -- the categories a church sets
    up under Groups -> Group Types (e.g. "Adult Groups", "Student
    Ministry", "Recovery", "Kids Classes") to organize its actual
    Groups. Used so the Connection Gaps tab can recommend real classes
    instead of a made-up list -- see get_class_catalog() below."""
    group_types = []
    next_url = None
    params = {"per_page": 100}

    while True:
        if next_url:
            data = _pco_request(next_url)
        else:
            data = pco_get("/groups/v2/group_types", params=params)

        for item in data.get("data", []):
            group_types.append({"id": item["id"], "name": item["attributes"].get("name") or "(unnamed)"})

        next_link = (data.get("links") or {}).get("next")
        if not next_link:
            break
        next_url = next_link

    return group_types


def _group_leader(group_id):
    """Find the leader of one Group -- looks through that Group's
    memberships for anyone whose role is (or contains) "leader", and
    looks up their phone number so a heads-up text can go straight to
    them. Returns None if no leader is found on file.

    # >>> The exact wording Planning Center uses for a membership's
    # "role" isn't documented publicly, so this checks for the word
    # "leader" anywhere in it (case-insensitive) to also catch labels
    # like "Co-Leader". If leaders aren't showing up correctly on the
    # Connection Gaps tab, check what role value your account actually
    # uses (Groups -> a group -> Members) and adjust this if needed --
    # same kind of thing that came up with Serving Teams earlier.
    """
    data = pco_get(f"/groups/v2/groups/{group_id}/memberships", params={"include": "person", "per_page": 100})
    included_people = {
        item["id"]: item for item in data.get("included", []) if item.get("type") == "Person"
    }

    for membership in data.get("data", []):
        role = (membership["attributes"].get("role") or "").lower()
        if "leader" not in role:
            continue

        person_ref = (membership.get("relationships", {}).get("person") or {}).get("data")
        if not person_ref:
            continue

        person_id = person_ref["id"]
        person_attrs = included_people.get(person_id, {}).get("attributes", {})
        try:
            details = get_person_details(person_id)
        except requests.exceptions.RequestException:
            details = {"phone_numbers": []}

        return {
            "person_id": person_id,
            "name": person_attrs.get("name") or details.get("name") or "(unknown)",
            "phone_numbers": details.get("phone_numbers", []),
        }

    return None  # no membership on file is marked as a leader for this group


def _parse_class_criteria(class_name):
    """Guess who a class is for straight from its name -- e.g. "Men's
    Classes 30-50" or "Couples Classes 30-50" -- by picking up on
    gender words, age ranges, and marital-status words. Returns a dict
    with "gender", "min_age", "max_age", and "marital_status", any of
    which are None if that class's name doesn't mention it (meaning
    that criterion is open to everyone).

    # >>> This is just pattern-matching on the class name, not a real
    # Planning Center field (Groups doesn't have a built-in "who this
    # is for" setting), so unusual naming may not parse correctly. Use
    # CLASS_CRITERIA_OVERRIDES in Section 1 for any class this doesn't
    # guess right for.
    """
    text = class_name.lower().replace("'", "")
    criteria = {"gender": None, "min_age": None, "max_age": None, "marital_status": None}

    if re.search(r"\b(women|womens|ladies)\b", text):
        criteria["gender"] = "Female"
    elif re.search(r"\b(men|mens)\b", text):
        criteria["gender"] = "Male"

    if re.search(r"\b(couples?|married)\b", text):
        criteria["marital_status"] = "Married"
    elif re.search(r"\bsingles?\b", text):
        criteria["marital_status"] = "Single"

    range_match = re.search(r"(\d{1,3})\s*-\s*(\d{1,3})", text)
    plus_match = re.search(r"(\d{1,3})\s*\+", text)
    under_match = re.search(r"under\s*(\d{1,3})", text)
    if range_match:
        criteria["min_age"] = int(range_match.group(1))
        criteria["max_age"] = int(range_match.group(2))
    elif plus_match:
        criteria["min_age"] = int(plus_match.group(1))
    elif under_match:
        criteria["max_age"] = int(under_match.group(1)) - 1

    return criteria


def _person_matches_criteria(person, criteria):
    """True if one person fits a class's gender/age-range/marital-
    status criteria (see _parse_class_criteria() above) -- any
    criterion left as None is treated as open to everyone."""
    if criteria["gender"]:
        person_gender = (person.get("gender") or "").strip().lower()
        if person_gender != criteria["gender"].lower():
            return False

    if criteria["marital_status"]:
        person_marital = (person.get("marital_status") or "").strip().lower()
        # substring match (not exact) so labels like "Remarried" still
        # count as "Married" -- see MEMBER_STATUSES for the same idea
        if criteria["marital_status"].lower() not in person_marital:
            return False

    age = person.get("age")
    if criteria["min_age"] is not None and (age is None or age < criteria["min_age"]):
        return False
    if criteria["max_age"] is not None and (age is None or age > criteria["max_age"]):
        return False

    return True


def get_class_catalog():
    """Build a list of every active Group church-wide, tagged with its
    real Group Type, its guessed gender/age/marital-status criteria,
    and its leader's contact info already looked up -- the pool that
    Connection Gaps recommends actual classes/groups from (see
    recommend_classes_for_person() below).

    Built once as a full catalog (rather than looked up per-person),
    since there could be thousands of people on the Connection Gaps
    tab but usually only a few dozen actual Groups church-wide --
    see _cached_class_catalog() below for the caching wrapper this
    depends on to stay fast.
    """
    group_types_by_id = {gt["id"]: gt["name"] for gt in _list_all_group_types()}

    catalog = []
    next_url = None
    params = {"where[archive_status]": "not_archived", "include": "group_type", "per_page": 100}

    while True:
        if next_url:
            data = _pco_request(next_url)
        else:
            data = pco_get("/groups/v2/groups", params=params)

        for group in data.get("data", []):
            group_type_ref = (group.get("relationships", {}).get("group_type") or {}).get("data")
            group_type_name = (
                group_types_by_id.get(group_type_ref["id"], "(No Group Type)")
                if group_type_ref else "(No Group Type)"
            )
            group_name = group["attributes"].get("name") or "(unnamed group)"

            leader = _group_leader(group["id"])
            time.sleep(0.1)  # a small pause -- one extra API call per group to find its leader

            catalog.append({
                "id": group["id"],
                "name": group_name,
                "group_type_name": group_type_name,
                "schedule": group["attributes"].get("schedule") or "",
                "leader": leader,
                "criteria": CLASS_CRITERIA_OVERRIDES.get(group_name) or _parse_class_criteria(group_name),
            })

        next_link = (data.get("links") or {}).get("next")
        if not next_link:
            break
        next_url = next_link

    catalog.sort(key=lambda g: (g["group_type_name"].lower(), g["name"].lower()))
    return catalog


@st.cache_data(ttl=1800)  # group rosters/leadership don't change minute to minute
def _cached_class_catalog():
    return get_class_catalog()


def recommend_classes_for_person(person, catalog):
    """Filter the full class catalog down to just the classes/groups
    that make sense for one person -- matching by gender, age, and
    marital status wherever a class's name spells that out (see
    _parse_class_criteria() above), so one person can land on more
    than one recommendation (e.g. a married 32-year-old man fitting
    both "Men's Classes 30-50" and "Couples Classes 30-50").

    For any class whose name doesn't mention gender/age/marital status
    at all, this falls back to the broader age-category matching from
    GROUP_TYPES_BY_AGE_CATEGORY in Section 1 instead (so a kids Sunday
    School class, for example, still shows up under "Children")."""
    recommended = []
    for group in catalog:
        criteria = group["criteria"]
        has_specific_criteria = (
            criteria["gender"] or criteria["marital_status"]
            or criteria["min_age"] is not None or criteria["max_age"] is not None
        )
        if has_specific_criteria:
            if _person_matches_criteria(person, criteria):
                recommended.append(group)
            continue

        # No gender/age/marital signal in this class's name -- fall back
        # to the broader age-category setting instead.
        category = age_category(person)
        wanted_type_names = {
            name.strip().lower() for name in GROUP_TYPES_BY_AGE_CATEGORY.get(category, [])
        }
        if not wanted_type_names or group["group_type_name"].strip().lower() in wanted_type_names:
            recommended.append(group)

    return recommended


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


def _gave_before_cutoff(person_id, cutoff_iso):
    """True if this person has at least one donation recorded before
    cutoff_iso -- used to tell a brand-new giver apart from a longtime
    giver who just happened to give again recently.

    # >>> This tries filtering Planning Center Giving donations directly
    # by person_id first (fastest, one request). That exact filter isn't
    # officially documented for this endpoint, so if your account
    # returns an error for it, this automatically falls back to paging
    # through that person's own donation history instead (slower, but
    # doesn't depend on that filter existing). Flagging this the same
    # way the Serving Teams name lookup was flagged earlier -- verify
    # this works against your real PCO data after the first live test.
    """
    try:
        data = pco_get(
            "/giving/v2/donations",
            params={"where[person_id]": person_id, "where[received_at][lt]": cutoff_iso, "per_page": 1},
        )
        return bool(data.get("data"))
    except requests.exceptions.HTTPError:
        pass  # that filter combo isn't supported on this account -- fall back below

    next_url = None
    params = {"per_page": 100}
    while True:
        if next_url:
            data = _pco_request(next_url)
        else:
            data = pco_get(f"/giving/v2/people/{person_id}/donations", params=params)

        for donation in data.get("data", []):
            received_at = donation.get("attributes", {}).get("received_at") or ""
            if received_at and received_at < cutoff_iso:
                return True

        next_link = (data.get("links") or {}).get("next")
        if not next_link:
            break
        next_url = next_link

    return False


def get_new_givers(lookback_days=NEW_GIVER_LOOKBACK_DAYS):
    """Find people whose very first tracked gift landed inside the
    lookback window (default: the last NEW_GIVER_LOOKBACK_DAYS days) --
    a simple way to spot brand-new givers worth a personal thank-you and
    a bit of orientation to where their generosity is going.

    This uses the Planning Center GIVING API, which is separate from the
    People API used everywhere else in this file, and needs its own
    permission: whoever created the PCO_APP_ID/PCO_SECRET Personal
    Access Token needs "giving-view" permission in Planning Center (see
    Setup Guide, Step 1). Without it, Planning Center returns a 403,
    which the New Givers tab below turns into a friendly explanation
    instead of a crash.

    How it decides who's "new":
      1. Pull every donation received in the last `lookback_days` days,
         and collect the unique people who gave in that window.
      2. For each of those people, check whether they have any *earlier*
         donation before the window started (see _gave_before_cutoff()
         above). If they don't, their very first gift falls inside the
         window, so they're a new giver. Someone who's given for years
         and simply gave again recently is correctly left off this list.
    """
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=lookback_days)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Step 1: everyone who gave since the cutoff.
    recent_giver_ids = set()
    next_url = None
    params = {"where[received_at][gte]": cutoff_iso, "per_page": 100}
    giving_donations_url = f"{PCO_BASE_URL}/giving/v2/donations"

    while True:
        if next_url:
            data = _pco_request(next_url)
        else:
            data = _pco_request(giving_donations_url, params=params)

        for donation in data.get("data", []):
            person_ref = (donation.get("relationships", {}).get("person") or {}).get("data")
            if person_ref:
                recent_giver_ids.add(person_ref["id"])
            # no person on the donation at all means it was given
            # anonymously -- nothing to text, so we just skip it

        next_link = (data.get("links") or {}).get("next")
        if not next_link:
            break
        next_url = next_link

    # Step 2: keep only the ones with no donation before the window.
    new_givers = []
    for person_id in recent_giver_ids:
        try:
            if _gave_before_cutoff(person_id, cutoff_iso):
                continue  # a longtime giver, not new
        except requests.exceptions.RequestException:
            continue  # couldn't check their history -- skip rather than guess

        try:
            details = get_person_details(person_id)
        except requests.exceptions.RequestException:
            details = {"name": "(unknown)", "phone_numbers": [], "grade": None, "child": False}

        new_givers.append({
            "id": person_id,
            "name": details.get("name") or "(unknown)",
            "phone_numbers": details.get("phone_numbers", []),
            "grade": details.get("grade"),
            "child": details.get("child", False),
        })
        time.sleep(0.05)  # small pause -- this makes one extra API call per new giver

    new_givers.sort(key=lambda p: p["name"].lower())
    return new_givers


@st.cache_data(ttl=900)  # giving activity doesn't change minute to minute
def _cached_new_givers():
    return get_new_givers()


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
    ("new_givers", "🙏 New Givers"),
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
    st.caption(
        "Each person also gets specific class/group recommendations pulled from your real "
        "Planning Center Groups, matched by gender, age, and marital status wherever a "
        "class's name spells that out (e.g. \"Men's Classes 30-50\", \"Couples Classes "
        "30-50\") -- so one person can match more than one class. See "
        "_parse_class_criteria() and CLASS_CRITERIA_OVERRIDES in Section 1/2 to adjust."
    )

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

    try:
        with st.spinner("Loading active classes and their leaders..."):
            class_catalog = _cached_class_catalog()
    except requests.exceptions.RequestException as e:
        st.caption(f"Couldn't load class recommendations right now: {e}")
        class_catalog = []

    # This list can be long, so we only show a batch at a time (see the
    # CONNECTION_GAPS_PAGE_SIZE setting up top) with a "Show more" button,
    # instead of rendering thousands of cards at once.
    if "connection_gaps_shown" not in st.session_state:
        st.session_state.connection_gaps_shown = CONNECTION_GAPS_PAGE_SIZE

    shown_count = st.session_state.connection_gaps_shown
    page_people = ungrouped_people[:shown_count]
    page_ids = {p["id"] for p in page_people}

    # Look up spouse info for anyone married currently on this page (only
    # this page, not the whole list -- a spouse lookup is a couple of
    # extra API calls, so we only pay that cost for people actually being
    # shown right now). If their spouse is ALSO on this page, they get
    # grouped into one card together below instead of two separate rows;
    # either way, seeing the spouse makes a couples class recommendation
    # make a lot more sense.
    spouse_by_id = {}
    for person in page_people:
        if "married" in (person.get("marital_status") or "").lower():
            try:
                spouse_by_id[person["id"]] = _cached_spouse(person["id"])
            except requests.exceptions.RequestException:
                spouse_by_id[person["id"]] = None
        else:
            spouse_by_id[person["id"]] = None

    already_shown_ids = set()
    for person in page_people:
        if person["id"] in already_shown_ids:
            continue  # already rendered together with their spouse, just below

        spouse = spouse_by_id.get(person["id"])
        paired_spouse = None
        if spouse and spouse["id"] in page_ids and spouse["id"] != person["id"]:
            paired_spouse = spouse
            already_shown_ids.add(spouse["id"])

        label = f"{person['name']} & {paired_spouse['name']}" if paired_spouse else person["name"]
        with st.expander(label):
            send_text_box(
                person["name"], person["phone_numbers"], key_prefix=f"gap_{person['id']}",
                default_message=connection_gap_message(person),
            )

            if paired_spouse:
                st.caption(f"Grouped with spouse {paired_spouse['name']}, also not in a Group.")
                send_text_box(
                    paired_spouse["name"], paired_spouse["phone_numbers"],
                    key_prefix=f"gap_{person['id']}_spouse",
                    default_message=connection_gap_message(paired_spouse),
                )
            elif spouse:
                spouse_phone = f" ({spouse['phone_numbers'][0]})" if spouse.get("phone_numbers") else ""
                st.caption(
                    f"Spouse on file: {spouse['name']}{spouse_phone} -- already in a Group, or just "
                    "not on this page of the list."
                )

            # Recommend classes for whichever of person/spouse are in this
            # household -- a couples class can match both, while a
            # gender-specific class (e.g. "Men's Classes") only matches
            # whichever one of them actually fits it.
            household = [person, paired_spouse] if paired_spouse else [person]
            recs_by_person_id = {
                p["id"]: {g["id"] for g in recommend_classes_for_person(p, class_catalog)}
                for p in household
            }
            recommended_ids = set().union(*recs_by_person_id.values()) if recs_by_person_id else set()
            recommended = [g for g in class_catalog if g["id"] in recommended_ids]

            if recommended:
                st.divider()
                st.markdown("**Recommend a class or group** (pick one or more)")
                class_names = [g["name"] for g in recommended]
                classes_by_name = {g["name"]: g for g in recommended}
                picked_names = st.multiselect(
                    "Classes/groups that fit -- matched by gender, age, and marital status",
                    class_names, key=f"gap_{person['id']}_class_pick",
                )

                for name in picked_names:
                    group = classes_by_name[name]
                    schedule_bit = f" — {group['schedule']}" if group["schedule"] else ""
                    st.markdown(f"*{group['group_type_name']}: {group['name']}{schedule_bit}*")

                    matching_people = [p for p in household if group["id"] in recs_by_person_id[p["id"]]]

                    for matched_person in matching_people:
                        st.caption(f"Invite to {matched_person['name']}")
                        send_text_box(
                            matched_person["name"], matched_person["phone_numbers"],
                            key_prefix=f"gap_{person['id']}_class_{group['id']}_prospect_{matched_person['id']}",
                            default_message=class_invite_message(matched_person, group["name"]),
                        )

                    if group["leader"]:
                        st.caption(f"Heads-up to the leader, {group['leader']['name']}")
                        if len(matching_people) == 2:
                            headsup_message = leader_headsup_couple_message(
                                matching_people[0], matching_people[1], group["name"], group["leader"]
                            )
                        else:
                            headsup_message = leader_headsup_message(
                                matching_people[0], group["name"], group["leader"]
                            )
                        send_text_box(
                            group["leader"]["name"], group["leader"]["phone_numbers"],
                            key_prefix=f"gap_{person['id']}_class_{group['id']}_leader",
                            default_message=headsup_message,
                        )
                    else:
                        st.caption(
                            "No leader on file for this class (see _group_leader() in Section 2) "
                            "-- just send the invite(s) above."
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

# --- Tab 8: New Givers ---------------------------------------------------
if active_tab == "new_givers":
    st.subheader(f"Gave for the first time in the last {NEW_GIVER_LOOKBACK_DAYS} days")
    st.caption(
        "Giving is one more sign someone is truly on campus and taking a next step. "
        "This thanks them personally, shares a bit about where their gift goes, and "
        "includes a stewardship tip -- a nice way to help them feel seen and invested."
    )
    st.caption(
        "Needs \"giving-view\" permission on the Planning Center token used by this "
        "dashboard -- see Step 1 of the Setup Guide if this tab shows a permission error."
    )

    if st.button("Refresh new givers"):
        st.cache_data.clear()

    try:
        with st.spinner("Checking Planning Center Giving for new donors..."):
            new_givers = _cached_new_givers()
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        if status in (401, 403):
            # Since every other tab on this dashboard already proves the
            # App ID/Secret pair itself is correct, a 401/403 specifically
            # here almost always means one thing: whoever created this
            # Personal Access Token doesn't have "giving-view" permission
            # in Planning Center (or the Giving product isn't enabled for
            # this account) -- not that the credentials are wrong.
            st.error(
                f"Planning Center Giving says this isn't allowed ({status} error). "
                "Whoever created the Personal Access Token in Step 1 of the Setup "
                "Guide needs \"giving-view\" permission on their Planning Center "
                "account (Account -> People -> Permissions), then may need to "
                "generate a new token before this tab will work."
            )
        else:
            st.error(f"Couldn't reach Planning Center Giving: {e}")
        new_givers = []
    except requests.exceptions.RequestException as e:
        st.error(f"Couldn't reach Planning Center Giving: {e}")
        new_givers = []

    new_givers = age_group_filter(new_givers, key_prefix="newgiver")

    if not new_givers:
        st.info("No brand-new givers in this window right now.")

    for person in new_givers:
        with st.expander(person["name"]):
            send_text_box(
                person["name"], person["phone_numbers"], key_prefix=f"newgiver_{person['id']}",
                default_message=new_giver_message(person),
            )

# --- Tab 9: Find a Person -----------------------------------------------
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
                # >>> TEMPORARY DIAGNOSTIC: shows exactly what Planning Center
                # is sending us for the fields Connection Gaps uses to match
                # classes (gender/marital status/age). Handy for figuring out
                # why someone isn't getting a class recommendation you'd
                # expect -- safe to delete this block once that's sorted out.
                st.caption(
                    f"[debug] gender: {person.get('gender') or '(not set)'} · "
                    f"marital_status: {person.get('marital_status') or '(not set)'} · "
                    f"age: {person.get('age') if person.get('age') is not None else '(unknown -- no/bad birthdate)'}"
                )
                # Streamlit won't allow a nested expander inside this one, so
                # this uses a checkbox toggle instead of another expander.
                if st.checkbox(
                    "🔧 [debug] show every raw field Planning Center sent back",
                    key=f"find_{person['id']}_debug",
                ):
                    try:
                        raw_attrs = _debug_raw_person_attributes(person["name"])
                    except requests.exceptions.RequestException as e:
                        raw_attrs = None
                        st.caption(f"Couldn't fetch raw attributes: {e}")
                    if raw_attrs:
                        for key, value in raw_attrs.items():
                            st.caption(f"{key}: {value}")
                send_text_box(person["name"], person["phone_numbers"], key_prefix=f"find_{person['id']}")

# --- Tab 10: Texting Inbox -------------------------------------------------
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
