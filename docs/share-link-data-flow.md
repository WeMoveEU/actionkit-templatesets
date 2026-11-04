# Share Link Data Flow: Click to ActionKit Database

## Naming Confusion: `source` Field

The `source` field in `share_link` is confusingly named. It does **not** mean "where the sharer came from." It means **which platform/method they are sharing TO** (e.g. whatsapp, copypaste, taf, instagram, bluesky).

This collides with `core_action.source`, which means "where the person who took the action came FROM."

To make matters worse, ActionKit **propagates** `share_link.source` into `core_action.source` on the downstream action — so the "sharing destination" of the original sharer becomes the "attribution source" of the recipient. The result happens to be correct (the recipient *did* come from WhatsApp) but for a completely different semantic reason.

The analytics models (`staging_shares`, `inferred_source_attribution`) rename this to `share_source` / `share_source_clean` to reduce ambiguity, but keep this naming collision in mind when reading raw ActionKit data.

## 1. User Clicks a Share Button (Frontend)

The templates construct a URL to `/share/link` with parameters like:
```
/share/link?type=fb&source=facebook&page_name=my-campaign&akid=123&action_id=456
```

Depending on the button type, the click is handled differently:

| Button | Mechanism | How `/share/link` is called |
|---|---|---|
| **Facebook** | Direct `<a href>` | Browser navigates to `/share/link`, gets redirected to Facebook |
| **Bluesky** | Direct `<a href>` or JS fetch | Similar redirect or JS fetches the tracking URL |
| **WhatsApp** | JS in `component-share_from_mailings_script.html` | `fetch()` to get the share URL, then redirects to `whatsapp://send/` |
| **Copy URL** | JS in `copy-to-clipboard.js` | `fetch()` gets the share URL, copies it to clipboard |
| **TAF (email)** | JS in `taf-button.js` | `fetch()` fires the tracking call, then opens `mailto:` |
| **Instagram** | JS in `send-share-to-action-kit.js` | `fetch()` fires tracking, link goes to external URL |

## 2. Server Receives `/share/link` (ActionKit Backend)

**Parameters accepted:**
- `type` — platform code: `fb`, `tw`, `bl`, `ot` (other)
- `page_name` — the campaign page name
- `akid` — user identifier
- `action_id` — links share to a specific action (takes priority over akid)
- `source` — tracking label (e.g. `taf`, `copypaste`, `instagram`, `whatsapp`, `bluesky`)
- `append` — extra path segments (used for events)

**Server-side processing:**
1. Resolves the user from `action_id` or `akid`
2. Creates a row in the **`share_link`** table with: `user_id`, `page_id`, `share_type_id`, `source`, `url`
3. Generates a special **"s" AKID** (e.g. `?akid=s31..ecM5JC`) embedded in the destination URL
4. Returns either:
   - **HTTP redirect** to the platform (Facebook sharer, Twitter intent, Bluesky compose) — for `type=fb/tw/bl`
   - **The tracking URL itself** (page URL with "s" AKID) — for `type=ot`, which JS then uses for clipboard/WhatsApp/etc.

## 3. Someone Clicks the Shared Link (Downstream)

When a recipient clicks the shared URL containing the "s" AKID:
- A row is written to the **`share_click`** table (`share_id`, `user_id`)

## 4. Recipient Takes Action

If the recipient then completes an action on the page:
- A row is written to the **`share_action`** table (`share_id`, `action_id`)
- The `source` from the originating `share_link` record propagates to **`core_action.source`**
- If no `source` was set on the `share_link`, the default source is `"share"`

## Database Tables

```
share_type          share_link              share_click         share_action
---------           ----------              -----------         ------------
id                  id                      id                  id
name (fb/tw/bl/ot)  share_type_id -->       share_id -->   share_id -->
                    page_id                 user_id             action_id
                    user_id
                    action_id
                    source  <-- THIS is where source= lands
                    url
```

## Why `source=` Matters

The `source` value stored on `share_link` is **not exposed in the outgoing shared URL** — it stays server-side. But it propagates to `core_action.source` when someone acts on the shared link. This is how you distinguish in reports whether downstream actions came from a WhatsApp share vs. a Facebook share vs. copy-paste, etc.

Without `source=`, downstream actions from those shares get the default `"share"` source, making it impossible to attribute them to a specific platform.

## Source Naming: `<platform>_<location>` (since 2026-10-30)

Every share button in the share partials sends `source=<platform>_<location>`, so
`share_link.source` says both where the supporter shared **to** and where they shared
**from**.

| Platform | Button |
|---|---|
| `facebook` | `component-share_button_facebook.html` |
| `bluesky` | `component-share_button_bluesky.html` (and `?share=bluesky` via the mailings script) |
| `whatsapp` | `component-share_button_whatsapp.html` → `component-share_from_mailings_script.html` |
| `instagram` | `component-share_button_instagram.html` |
| `taf` | `component-share_button_taf.html` |
| `copypaste` | `component-share_button_copy_url.html` |

| Location | Meaning | Set by |
|---|---|---|
| `popup` | Share popup on the petition page, right after signing | `partial-share_popup-inside-petition.html` |
| `thanks` | Share step on the thanks page | `partial-share_standard.html` (default) |
| `mailing` | A `/thanks/PAGE?share=<network>` link from a mailing | `partial-share_standard.html`, when `?share=<network>` arrives without `share_location` |

Each share partial sets the `shareLocation` template variable before including the
buttons. Buttons that open the thanks page in a new tab (WhatsApp always; e-mail and
Instagram when handing off to a daisy-chained page) pass it on as
`&share_location=<location>`, so the share that page fires keeps its real origin.

So `whatsapp_popup`, `facebook_thanks`, `taf_mailing`, etc. Rows without a suffix
predate the change (and `fb`/`bl` rows had no source at all).

Not affected: the `source=` that the WhatsApp/Bluesky script and the TAF mailto body
(`tag_links:"source=mailto"`) append to the URL the **recipient** receives. That is
recipient attribution and stays platform-only. Event pages (`event_search.html`,
`event_invite.html`) still send no `source`.

`scripts/test_share_tracking.py` clicks every button in each location and checks the
resulting `share_link.source`.
