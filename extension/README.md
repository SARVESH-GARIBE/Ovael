# Ovael Privacy Monitor (browser extension)

Measures every website you visit, in your own browser, and shows what it shares: which companies
receive your data and how much is sent to them, trackers, cookies, what scripts store on your device
(localStorage, IndexedDB, Cache API), what was served from your cache, and fingerprinting. Each visit
is scored by the same website model as the Ovael scanner.

## Install (Chrome, Edge, Brave)

1. Start the backend (`backend/README.md`), default `http://localhost:8000`.
2. Open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and pick this
   `extension/` folder.
3. Browse. The toolbar badge shows the number of trackers on the current page; click it for the
   site's report. **All sites** opens the dashboard, which also holds the settings (backend URL,
   excluded domains, pause, model scoring on/off).

## How it measures

| What | How |
|---|---|
| Requests, third parties, data sent | `webRequest`: every request a tab makes, its URL size, body size and query parameters. First- vs third-party is by registrable domain (Public Suffix List), like the crawler |
| Data received, cache | `Content-Length` of responses (missing for some), and Chrome's `fromCache` flag |
| Trackers and companies | DuckDuckGo Tracker Data Set, the same file the crawler uses |
| Storage and fingerprinting | The crawler's `instrumentation.js`, injected into every frame. It only counts API calls and never reads stored values, drawn text or pixels |
| Cookies | Flags, domain and expiry of the cookies held for the domains the page contacted. Values are never read |
| Model verdict | The crawler's feature row, taken 5 s after the page's load event (the crawler's measurement window), scored by `POST /api/extension/score` |

**Privacy:** history is stored only in this browser (`chrome.storage.local`). With scoring on, the backend
receives just the site's domain and numeric counts: no URLs, page text or cookie values. It does not
save them.

**Differences from the crawler**, to keep in mind when reading the verdict:
- It measures your real browser: you're logged in, have accepted consent banners, and have a warm cache.
- Cookie counts include cookies these companies already set on earlier visits.

## Refreshing the bundled data

`data/` and `content/instrument.js` are generated from the crawler's reference files:

```bash
backend/.venv/bin/python extension/tools/build_data.py
```

The tracker data is DuckDuckGo's Tracker Data Set, licensed CC BY-NC-SA 4.0 (non-commercial use only).
