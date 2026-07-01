# Church Care Dashboard — Setup Guide

A simple dashboard that connects Planning Center (your people data) and
Clearstream (your texting platform) so you can see who needs a birthday
note, search for someone, and check the texting inbox — all from your iPad.

No coding experience needed. Follow these steps in order.

---

## Step 1: Get your Planning Center key

1. Log into Planning Center as an admin.
2. Go to `api.planningcenteronline.com/oauth/applications`.
3. Click **Personal Access Tokens** → **New Personal Access Token**.
4. Give it a name like "Care Dashboard."
5. Copy the **App ID** and the **Secret** somewhere safe — you'll need both
   in Step 3. The Secret is only shown once.

> Note: this token has the exact same permissions as the person who
> created it. If you want the dashboard to see Giving data later, the
> account that creates the token needs giving-view permission.

---

## Step 2: Get your Clearstream key

1. Log into Clearstream.
2. Go to `app.clearstream.io/settings/api/keys`.
3. Create a new API key and copy it somewhere safe.

> Clearstream applies low rate limits to brand-new API texting. If you
> plan to use this for real outreach, message Clearstream support and ask
> them to raise your limits.

---

## Step 3: Add your keys to Replit's Secrets tab

Secrets are how this app reads your keys without ever putting them in
the code (so they're never visible on GitHub).

1. In your Replit project, click the **lock icon** in the left sidebar
   (labeled "Secrets").
2. Add four secrets, one at a time, using **Add new secret**:

   | Key | Value |
   |---|---|
   | `PCO_APP_ID` | the App ID from Step 1 |
   | `PCO_SECRET` | the Secret from Step 1 |
   | `CLEARSTREAM_API_KEY` | the key from Step 2 |
   | `CHURCH_NAME` | your church's name (used in text messages) |

3. Each secret needs the key name typed exactly as shown (all capitals,
   underscores, no spaces).

---

## Step 4: Run it

1. Click the green **Run** button at the top of Replit.
2. The first run installs `streamlit` and `requests` — this can take a
   minute.
3. A preview window opens showing the dashboard with three tabs:
   **Birthdays**, **Find a Person**, and **Texting Inbox**.
4. If you see a red error box at the top instead, it will tell you which
   secret is missing — go back to Step 3.

---

## Step 5: Try it out

- **Birthdays tab** — shows everyone with a birthday in the next 7 days.
  Click a name to expand it and send them a text.
- **Find a Person tab** — type a real name and search. Click the result
  to see their info and send a text.
- **Texting Inbox tab** — shows your most recent Clearstream
  conversations.

A good first test: search for yourself in **Find a Person**, then send
yourself a test text to confirm both keys are working end-to-end.

---

## Step 6: Add it to your iPad home screen (optional but handy)

1. Open the Replit preview URL in **Safari** (not the Replit app).
2. Tap the **Share** button.
3. Tap **Add to Home Screen**.

Now it opens like a regular app with one tap.

---

## When something breaks

Copy the **red error text** exactly as it appears and share it — that's
almost always enough to fix it.

Common ones:
- *"Missing secret(s): ..."* — a Secrets tab entry is missing or
  misspelled.
- *Planning Center 401 error* — the App ID/Secret pair is wrong, or the
  token was deleted.
- *Clearstream 401 error* — the API key is wrong or was revoked.

---

## What's in this project

| File | What it is |
|---|---|
| `main.py` | The dashboard itself. One file, organized into labeled sections. |
| `requirements.txt` | The two Python packages this needs (`streamlit`, `requests`). |
| `.replit` | Tells Replit how to run the app. |
| `.streamlit/config.toml` | Display settings for a clean preview. |
| `apple-shortcut-text-a-member.md` | Build guide for a quick-text Apple Shortcut. |

## What's next

See `COWORK-PROJECT-BRIEF.md` for the roadmap — Phase 2 adds a
Follow-up Queue tab, Phase 3 flags people who've stopped attending, and
Phase 4 covers a few optional extras.
