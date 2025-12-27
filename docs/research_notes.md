# Supernote Research Notes

**Last Updated:** December 26, 2025
**Focus:** 2024-2025 Sources

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Supernote Cloud API](#supernote-cloud-api)
3. [File Formats](#file-formats)
4. [To-Do App & Task Management](#to-do-app--task-management)
5. [Sync Tools & Libraries](#sync-tools--libraries)
6. [Document Link Formats](#document-link-formats)
7. [GitHub Repositories](#github-repositories)
8. [Technical Limitations & Gaps](#technical-limitations--gaps)

---

## Executive Summary

Supernote does not provide official public API documentation. All available API clients and sync tools are community-built through reverse engineering. The Supernote Cloud API supports basic file operations (list, download, upload) but does not expose direct access to to-do task data. The To-Do app syncs through the Supernote Partner app, but no public API exists for programmatic task access.

**Key Finding:** Accessing Supernote to-dos programmatically will likely require:
1. Using the Supernote Cloud API to download files
2. Parsing `.note` files using `supernotelib` to extract task data
3. Or intercepting/reverse-engineering the Partner app's sync protocol

---

## Supernote Cloud API

### Overview
Supernote Cloud is the official data storage platform for Supernote devices. Auto-sync is only available through Supernote Cloud (not third-party providers like Dropbox or Google Drive).

### Unofficial API Libraries

#### 1. sncloud (Python)
- **PyPI:** https://pypi.org/project/sncloud/
- **GitHub:** https://github.com/julianprester/sncloud
- **Latest Version:** 0.2.1 (April 28, 2025)
- **License:** Not specified

**Authentication:**
```python
from sncloud import SNClient

client = SNClient()
client.login("email@example.com", "password")
```

**Available Methods:**
| Method | Description |
|--------|-------------|
| `ls()` | List files and folders in a directory |
| `get()` | Download files locally |
| `put()` | Upload a file to the cloud |
| `mkdir()` | Create a directory on the cloud |

**Limitations:**
- Cannot delete, move, or rename files
- Only covers filesystem operations
- Does not expose to-do/task data directly

**CLI Configuration:**
- Access tokens stored in `~/.config/sncloud/config.json`
- Automatic token refresh supported

#### 2. supernote-cloud-api (JavaScript/Node.js)
- **GitHub:** https://github.com/adrianba/supernote-cloud-api
- **NPM Package:** `supernote-cloud-api`
- **Created by:** Observing network calls from Supernote web app

**Available Functions:**
```javascript
login(email, password)      // Returns access token
fileList(token, directoryId) // List files (directoryId optional, defaults to root)
fileUrl(token, id)          // Get download URL for file
syncFiles(token, localPath) // Sync cloud files to local filesystem
```

**Note:** May break if Supernote modifies their API endpoints.

#### 3. supernote-cloud-python
- **GitHub:** https://github.com/bwhitman/supernote-cloud-python
- Python wrapper for the unofficial Supernote Cloud API
- Supports login, list, download, and upload operations

### Private Cloud / Self-Hosting
Supernote offers a self-hosted option for users who want to keep notes on their own hardware.

**Key Ports:**
- **Port 18072:** Maps to automatic synchronization via WebSocket protocol

---

## File Formats

### .note Files
The primary Supernote notebook format. Contains handwritten notes, vector data, and metadata.

**Parsing Tool:** `supernotelib` (Python)
- **PyPI:** https://pypi.org/project/supernotelib/
- **GitHub:** https://github.com/jya-dev/supernote-tool
- **Latest Version:** 0.6.2
- **License:** Apache License 2.0

**Supported Devices/Firmware:**
- Supernote A5 (Firmware SN100.B000.432_release)
- Supernote A6X (Firmware Chauvet 2.23.36)
- Supernote A5X (Firmware Chauvet 2.23.36)
- Supernote A6X2 (Firmware Chauvet 3.25.39)
- Supernote A5X2 (Firmware Chauvet 3.25.39)

**Converting .note to Other Formats:**
```bash
# Convert to PNG
supernote-tool convert your.note output.png

# Convert to PDF (vector)
supernote-tool convert --pdf-type vector your.note output.pdf

# Convert to SVG
supernote-tool convert your.note output.svg

# Extract text (from real-time recognition notes)
supernote-tool convert -t txt your.note output.txt

# Dump metadata as JSON (for developers)
supernote-tool analyze your.note
```

**Programmatic Usage:**
```python
import supernotelib as sn

with open('your.note', 'rb') as f:
    metadata = sn.parse_metadata(f, policy='strict')
    print(metadata.to_json(indent=2))
```

### .spd Files
Supernote Atelier (drawing) format, convertible to PNG.

### Related Files
- `.spd-shm` / `.spd-wal` - SQLite auxiliary files for concurrent access

### Supported Import Formats
- PDF, EPUB, DOC, TXT
- PNG, JPG, JPEG, WEBP
- Comic book archive (.cbz)
- FictionBook2 (.fb2)
- OpenXPS (.xps)

---

## To-Do App & Task Management

### Overview
Introduced in recent firmware, the To-Do app allows task management on Supernote devices with cloud sync to the Supernote Partner app.

### Features
- **Three predefined lists:** Inbox, Planned, All
- **Custom lists:** Up to 13 visible lists (scrollbar for more)
- **Task creation:** Direct entry or converted from handwritten notes using lasso tool
- **Due dates:** Calendar picker, categorized as "Today," "Overdue," or "Upcoming"
- **Status tracking:** Strikethrough indicator for completed tasks
- **Sync:** Tasks sync with Supernote Cloud and Partner app

### Star Mark Recognition
- **Setting location:** Settings > Display & input > Preferred setting > Star mark recognition
- **Updated (Dec 2024):** Moved to Pen Preferences menu (Toolbar > Pen Selection Menu)
- Stars can be used as navigation markers alongside Titles, Keywords, Bookmarks, and Annotations

### Handwriting Recognition
- Supernote converts handwriting to text for task titles
- Reported accuracy: ~94% (based on community testing)

### Partner App Sync
The Supernote Partner app (iOS, Android, Windows) syncs tasks with the device.

**Recent Updates:**
- **Version 2.1.0 (Aug 2024):** Cloud infrastructure upgrade
- **Version 2.2.12 (Dec 2024):** Login-free mode, verification code login

### Technical Access to To-Do Data
**No public API exists for direct to-do access.** Potential approaches:
1. Parse `.note` files for star-marked or task-related content
2. Intercept Partner app network traffic to reverse-engineer the sync protocol
3. Use the Browse & Access WiFi feature to access device filesystem

---

## Sync Tools & Libraries

### 1. jbchouinard/supernote-sync (Rust/Docker)
- **GitHub:** https://github.com/jbchouinard/supernote-sync
- **Method:** Uses Supernote Browse & Access feature over local WiFi
- **Database:** SQLite (default) or PostgreSQL via SQLAlchemy

**Requirements:**
- Device IP address
- Port (default: 8089)
- Device name
- Computer and device on same network

**Synced File Types:**
```
note, spd, spd-shm, spd-wal, pdf, epub, doc, txt, png, jpg, jpeg, webp
```

**Sync Modes:**
- **Pull Mode:** Downloads from device (Note, Document, MyStyle, EXPORT, SCREENSHOT)
- **Push Mode:** Uploads to INBOX only (device doesn't allow overwriting)

**Features:**
- Automatic conversion of notebooks to PDF
- Configurable sync intervals (default: 60 seconds)
- Docker image available

### 2. dylanmazurek/supernote-sync (Golang)
- **GitHub:** https://github.com/dylanmazurek/supernote-sync
- **Language:** 100% Go
- Syncs Supernote Cloud files to local directory

**Features:**
- Email authentication
- Device binding verification
- MD5 hash-based change detection
- Selective folder sync
- Configurable sync frequency

### 3. RohanGautam/supernote-sync-tool (Python)
- **GitHub:** https://github.com/RohanGautam/supernote-sync-tool
- Simple terminal app for syncing notes locally
- Includes PDF conversion
- Requires Python 3.7 with conda

### 4. ariccb/supernote-to-noteplan-sync
- **GitHub:** https://github.com/ariccb/supernote-to-noteplan-sync
- Utility scripts to sync Supernote .note files to NotePlan

---

## Document Link Formats

### Internal Notebook Links
Supernote supports creating links between notebooks using the lasso tool:
1. Circle handwritten text with lasso tool
2. Tap "Link" icon in pop-up menu
3. Select link style from three available options

**Supported Link Targets:**
- Other notebook pages
- PDFs and eBooks
- Web pages

**Navigation:**
- Single-tap to follow link
- "Back" button to return to previous page
- Link chains supported (multiple linked pages in sequence)

**Limitations:**
- Links only work in the visible Main Layer
- Can only link TO notes (not other file types as source)
- No documented `note://` URL scheme for programmatic access

### PDF Hyperlinks
Supernote follows local links within PDF documents.

---

## GitHub Repositories

### Essential Repositories

| Repository | Language | Description |
|------------|----------|-------------|
| [julianprester/sncloud](https://github.com/julianprester/sncloud) | Python | Unofficial Supernote Cloud API client |
| [adrianba/supernote-cloud-api](https://github.com/adrianba/supernote-cloud-api) | TypeScript | JavaScript API for Supernote Cloud |
| [jya-dev/supernote-tool](https://github.com/jya-dev/supernote-tool) | Python | Parse and convert .note files (349 stars) |
| [jbchouinard/supernote-sync](https://github.com/jbchouinard/supernote-sync) | Rust | WiFi sync with SQLite database |
| [dylanmazurek/supernote-sync](https://github.com/dylanmazurek/supernote-sync) | Go | Cloud sync CLI tool |

### Resource Collections

| Repository | Description |
|------------|-------------|
| [fharper/awesome-supernote](https://github.com/fharper/awesome-supernote) | Curated list of Supernote projects and templates |
| [dwongdev/sugoi-supernote](https://github.com/dwongdev/sugoi-supernote) | Tips, tricks, and guides for Supernote |

### Conversion & Visualization Tools

| Repository | Description |
|------------|-------------|
| [mmujynya/SNEX](https://github.com/mmujynya) | Convert Supernote notebooks to Excalidraw format |
| [cristianvasquez/supernote-tldraw](https://github.com/cristianvasquez) | Render .note files in canvas interface |
| [cristianvasquez/supernote-web-viewer](https://github.com/cristianvasquez) | Browser-based .note file viewer |
| [RohanGautam/supernote-sync-tool](https://github.com/RohanGautam/supernote-sync-tool) | Terminal sync app with PDF conversion |
| [HackXIt/supernote-converterLib](https://github.com/HackXIt/supernote-converterLib) | Fork of supernote-tool |

### Integration Plugins

| Repository | Description |
|------------|-------------|
| [philips/obsidian-supernote](https://github.com/philips) | Obsidian plugin for .note to PNG conversion |

### Other Notable Projects

| Repository | Description |
|------------|-------------|
| [Am4rantheus/Supernote-Icon-Editor-for-Keywords](https://github.com/Am4rantheus) | Icon editor for keyword setup |
| [xypine/supernote-utils](https://github.com/xypine/supernote-utils) | Supernote utilities |
| [bromanko/supernote](https://github.com/bromanko/supernote) | Supernote tools |
| [camerahacks/super-supernote](https://github.com/camerahacks/super-supernote) | Tools to enhance Supernote devices |

---

## Technical Limitations & Gaps

### No Public API Documentation
Supernote does not provide official API documentation. All community tools are based on reverse engineering.

### To-Do Data Access
- No direct API for to-do lists
- Tasks sync through proprietary Partner app protocol
- May require intercepting network traffic or parsing .note files

### Database Schema
- No public documentation on internal database schema
- jbchouinard/supernote-sync uses SQLite/PostgreSQL for sync state tracking (not Supernote's internal format)
- `.spd-shm` and `.spd-wal` files suggest SQLite is used internally

### File Manipulation Limitations
- Cannot delete, move, or rename files via API
- Device doesn't allow overwriting files via sync
- Push operations limited to INBOX folder

### Sync Limitations
- Auto-sync only available through Supernote Cloud (not Dropbox/Google Drive)
- Browse & Access requires same network
- WebSocket protocol on port 18072 for auto-sync (undocumented)

---

## Recommendations for This Project

Based on the research, here are recommended approaches for syncing Supernote to-dos with Apple Reminders:

### Approach 1: Parse .note Files
1. Use `sncloud` to download .note files from Supernote Cloud
2. Use `supernotelib` to parse the files and extract metadata
3. Look for star marks or task-related content in the JSON metadata
4. Create corresponding Apple Reminders using EventKit/Reminders APIs

### Approach 2: Browse & Access Protocol
1. Connect to Supernote via WiFi using Browse & Access
2. Use the local API (port 8089) to access files
3. Parse .note files for task data
4. Sync with Apple Reminders

### Approach 3: Reverse Engineer Partner App
1. Capture network traffic from Supernote Partner app
2. Identify to-do sync endpoints and data format
3. Implement sync protocol directly
4. Map tasks to Apple Reminders

### Challenges
- No direct to-do API exists
- Task data format in .note files is undocumented
- Star mark recognition may not map cleanly to tasks
- Real-time sync would require polling or monitoring

---

## Sources

### Official Supernote Resources
- [Supernote Cloud](https://support.supernote.com/en_US/Tools-Features/supernote-cloud)
- [Supernote Cloud Auto Sync](https://support.supernote.com/en_US/Whats-New/supernote-cloud-auto-sync)
- [The To-Do App](https://support.supernote.com/en_US/Whats-New/the-to-do-app)
- [Supernote Partner App for Desktop](https://support.supernote.com/en_US/Tools-Features/supernote-partner-app-for-desktop)
- [Supernote Partner App for Mobile](https://support.supernote.com/en_US/Tools-Features/1753209-supernote-partner-app-for-mobile)
- [Inserting Links to Notebooks](https://support.supernote.com/en_US/Tools-Features/inserting-links-to-notebooks)
- [A5 X & A6 X Changelog](https://support.supernote.com/en_US/change-log/changelog-for-a5-x-and-a6-x)
- [Setting Up Your Own Supernote Private Cloud](https://support.supernote.com/Whats-New/setting-up-your-own-supernote-private-cloud-beta)

### GitHub Repositories
- [julianprester/sncloud](https://github.com/julianprester/sncloud)
- [adrianba/supernote-cloud-api](https://github.com/adrianba/supernote-cloud-api)
- [jya-dev/supernote-tool](https://github.com/jya-dev/supernote-tool)
- [jbchouinard/supernote-sync](https://github.com/jbchouinard/supernote-sync)
- [dylanmazurek/supernote-sync](https://github.com/dylanmazurek/supernote-sync)
- [fharper/awesome-supernote](https://github.com/fharper/awesome-supernote)
- [dwongdev/sugoi-supernote](https://github.com/dwongdev/sugoi-supernote)
- [RohanGautam/supernote-sync-tool](https://github.com/RohanGautam/supernote-sync-tool)
- [ariccb/supernote-to-noteplan-sync](https://github.com/ariccb/supernote-to-noteplan-sync)
- [camerahacks/super-supernote](https://github.com/camerahacks/super-supernote)

### Package Repositories
- [sncloud on PyPI](https://pypi.org/project/sncloud/)
- [supernotelib on PyPI](https://pypi.org/project/supernotelib/)

### Community & Blog Resources
- [Supernote Blog - Productivity Features](https://supernote.com/blogs/supernote-blog/supercharge-your-productivity-supernotes-all-in-one-to-do-list-management-and-more-1)
- [eWritable - TODO List App Review](https://ewritable.com/todo-list-app-included-in-latest-supernote-firmware/)
- [sugoi-supernote Self-Hosting Guide](https://github.com/dwongdev/sugoi-supernote/blob/main/Guides/how_to_selfhost_sync.md)
