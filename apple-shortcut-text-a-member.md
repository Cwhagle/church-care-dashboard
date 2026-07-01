# Apple Shortcut: Text a Member

This builds a quick Shortcut for your iPhone/iPad so you can send a
pastoral text on the go — without opening the dashboard at all.

It works by calling the same Clearstream API the dashboard uses.

---

## What you'll need

- The Clearstream API key from `app.clearstream.io/settings/api/keys`
  (same one used in Replit Secrets — Step 2 of the README).
- Your church name, exactly how you want it to show up as the
  message's reply name.

---

## Build steps

1. Open the **Shortcuts** app on your iPhone/iPad.
2. Tap the **+** to create a new shortcut. Name it something like
   "Text a Member."
3. Add action: **Ask for Input**
   - Input Type: **Text**
   - Prompt: "Who are you texting? (phone number)"
   - Save the result as a variable, e.g. `Phone Number`.
4. Add another **Ask for Input**
   - Input Type: **Text**
   - Prompt: "What do you want to say?"
   - Save as `Message Text`.
5. Add action: **Text** (the plain text-building action, not iMessage)
   - Build the message body using your `Message Text` variable.
6. Add action: **Get Contents of URL**
   - URL: `https://api.getclearstream.com/v1/threads`
   - Method: **POST**
   - Headers:
     - `X-Api-Key` → your Clearstream API key
     - `Content-Type` → `application/json`
   - Request Body: **JSON**, with these fields:
     - `mobile_number` → your `Phone Number` variable (must include the
       country code, e.g. `+12515550100` — see formatting note below)
     - `reply_header` → your church's name (type it directly)
     - `reply_body` → your `Message Text` variable
7. Add action: **Show Notification** (optional)
   - Show the result of the API call so you know it sent.

---

## Phone number formatting

Clearstream needs the number in **E.164 format**: a `+`, then the
country code, then the number with no spaces or dashes.

Example: `(251) 555-0100` becomes `+12515550100`.

If you want the Shortcut to handle this automatically, add a **Replace
Text** action before the Ask for Input result is used, to strip out any
spaces, dashes, or parentheses, then add **Text** action to prepend
`+1` if the number doesn't already start with `+`.

---

## A note on consent

Clearstream will not deliver a message to anyone who has opted out of
texts — that's enforced by Clearstream itself, and it's there for a good
reason. Only use this Shortcut for people who've agreed to receive
texts from the church.

---

## Testing it

Run the Shortcut once and send a text to your own phone number first,
to confirm the API key and formatting are correct before using it on a
real member.
