# 🛰️ DevRadar — GitHub Developer Activity Radar & Trending Monitor

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41CD52?logo=qt&logoColor=white)](https://www.riverbankcomputing.com/software/pyqt/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20|%20Linux%20|%20macOS-lightgrey)]()
[![GitHub Stars](https://img.shields.io/github/stars/TrueFurina/DevRadar-GitHub-Trending-Monitor?style=social)](https://github.com/TrueFurina/DevRadar-GitHub-Trending-Monitor)

> **English** | [中文版](README.zh.md)

---

**DevRadar** is a desktop application that turns GitHub into your personal developer radar. It monitors trending repositories, tracks developer activity in real time, and generates insightful reports — all from a sleek dark-themed GUI, no browser needed.

Whether you're hunting for the next viral open-source project, keeping tabs on what your favorite developers are committing, or building a personal tech briefing, DevRadar puts the pulse of GitHub on your desktop.

---

## ✨ Features

| # | Feature | Description |
|---|---------|-------------|
| 🔥 | **GitHub Trending** | Scrape and browse trending repos by language (daily / weekly / monthly) with automatic failover between HTML scraping and a fallback API |
| 🔍 | **Global Search** | Search GitHub repositories with filters (language, stars range, sort order); rate-limit aware with exponential backoff retry |
| 🎯 | **Targeted Monitoring** | Monitor any GitHub user or repository for real-time events — pushes, releases, issues, PRs, stars, forks, and more |
| 📡 | **Live Event Stream** | Real-time event feed with importance-based highlighting (gold for releases/PRs, cyan for issues, gray for pushes) and desktop notifications |
| ⭐ | **Star Snapshot & Chart** | Automatic periodic star-count collection; visualize growth trends with matplotlib-powered dark-theme charts |
| 📊 | **Project Insight** | Deep-dive into any repo: star history, health metrics (open issues, forks, watchers, license), top contributors, and topic tags |
| 📋 | **Personal Tech Briefing** | One-click Markdown report generation covering your monitored repos, trending top 5, bookmarks, and search history |
| 🔖 | **Local Bookmarks** | Save interesting repositories locally with notes, searchable offline |
| 🛡 | **Full Fault Tolerance** | Rate-limit warnings, auto-reconnect with exponential backoff, graceful degradation, and comprehensive logging |

---

## 🖼️ Screenshots

<!-- Add screenshots here after pushing -->
```
[ Coming soon — see the Chinese version for a preview image ]
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DevRadar Desktop App                         │
├───────────────────────┬───────────────────────┬─────────────────────┤
│                       │                       │                     │
│   🎨 GUI Layer        │   🔧 Common Layer     │   🖥 Server Layer    │
│   (PyQt6)             │                       │                     │
│                       │                       │                     │
│  ┌─────────────────┐  │  ┌─────────────────┐  │  ┌─────────────────┐ │
│  │ Search Panel     │  │  │ Config Manager  │  │  │ GitHub API      │ │
│  │ Trending Panel   │  │  │ (env → JSON)    │  │  │ (REST, caching) │ │
│  │ Monitor Panel    │  │  │ Logger          │  │  │ Trending Scraper│ │
│  │ Stream Panel     │  │  │ (Rotating file) │  │  │ (HTML + API)    │ │
│  │ Insight Dialog   │  │  │ Protocol        │  │  │ DB Manager      │ │
│  │ Report Generator │  │  │ (JSON Socket)   │  │  │ (SQLite, WAL)   │ │
│  └────────┬─────────┘  │  └─────────────────┘  │  │ Monitor Sched.  │ │
│           │            │                       │  │ Snapshot Mgr    │ │
│           ▼            │                       │  │ Report Gen.     │ │
│  ┌─────────────────┐  │                       │  └─────────────────┘ │
│  │ Socket Client    │  │                       │           ▲          │
│  │ (auto-reconnect) │  │                       │           │          │
│  └────────┬─────────┘  │                       │  ┌────────┴────────┐ │
│           │            │                       │  │  TCP Socket     │ │
│           └────────────┼───────────────────────┼──┤  (JSON / \n)    │ │
│                        │                       │  │  127.0.0.1:9669 │ │
└────────────────────────┘───────────────────────┘  └─────────────────┘ │
                                                     │                  │
                                              ┌──────┴──────┐           │
                                              │   SQLite    │           │
                                              │  devradar.db│           │
                                              │  6 tables   │           │
                                              └─────────────┘           │
└───────────────────────────────────────────────────────────────────────┘
```

### Communication Protocol

The client and server communicate over **TCP Socket** with JSON-delimited messages (`\n`-terminated). The protocol supports:

- **Commands**: add/remove/list monitors, search repos, fetch trending, generate reports, manage bookmarks
- **Push events**: real-time event delivery from server to client
- **Heartbeat**: keep-alive every 30 seconds
- **Status**: rate-limit warnings, connection state

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- A [GitHub Personal Access Token](https://github.com/settings/tokens) (optional but recommended — without it, API rate limit is only 60 req/hour)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/TrueFurina/DevRadar-GitHub-Trending-Monitor.git
cd DevRadar-GitHub-Trending-Monitor

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Configure your GitHub token
#    Create data/config.json or set the GITHUB_TOKEN environment variable
echo '{"github_token": "ghp_xxxxxxxxxxxx"}' > data/config.json
```

### Run

```bash
python run.py
```

Or double-click `启动DevRadar.bat` on Windows.

---

## ⚙️ Configuration

Configuration is loaded with the following priority: **Environment variable > config.json > Defaults**.

### config.json (optional, created automatically)

| Key | Default | Description |
|-----|---------|-------------|
| `github_token` | `""` | GitHub Personal Access Token |
| `poll_interval_seconds` | `300` | Monitor polling interval (5 min) |
| `trending_refresh_seconds` | `600` | Trending auto-refresh interval (10 min) |
| `snapshot_interval_hours` | `6` | Star snapshot interval |
| `report_period` | `weekly` | Default report period |
| `default_language` | `python` | Default trending language |
| `notification_enabled` | `true` | Desktop notifications |
| `max_history_days` | `30` | Event retention period |
| `socket_host` | `127.0.0.1` | Server bind address |
| `socket_port` | `9669` | Server port |
| `trending_source` | `html` | Trending source: `html` or `api` |

### Environment Variable

```bash
# Windows
set GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# Linux / macOS
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

---

## 📖 Usage Guide

### First Launch

1. **Start the app** → `python run.py`
2. **Configure Token** → If not set, press Enter to continue (limited functionality)
3. **Browse Trending** → Select language/period in the Trending panel, click Refresh
4. **Search Projects** → Type in the search bar, use filters to narrow results
5. **Add Bookmarks** → Right-click on any result → Bookmark
6. **Add Monitor** → In the Monitor panel, enter a username (e.g., `torvalds`) or repo (`torvalds/linux`)
7. **Generate Report** → Menu `File → Generate Report` or `Ctrl+R`

### Key Operations

| Action | Method |
|--------|--------|
| Search repositories | Search bar + Enter |
| Browse trending | Trending panel → select language/period → Refresh |
| Add monitor | Monitor panel → enter username or repo |
| Edit filter rules | Monitor list → right-click → Edit filters |
| Bookmark a repo | Search/Trending result → right-click → Bookmark |
| Generate report | Menu `File → Generate Report` (Ctrl+R) |
| View insight | Trending list → right-click → View Insight |
| Open in browser | Double-click any repo, or right-click → Open in Browser |

---

## 🗄️ Database Design

The application uses **SQLite** (`data/devradar.db`, WAL mode) with 6 tables:

### monitors
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PK | Primary key |
| target | TEXT UNIQUE | Target (username or owner/repo) |
| type | TEXT | `user` or `repo` |
| filters | TEXT (JSON) | Filter rules (event types, keywords) |
| added_at | TIMESTAMP | Created timestamp |

### events
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PK | Primary key |
| monitor_id | INTEGER FK | References monitors |
| event_type | TEXT | GitHub event type |
| payload | TEXT (JSON) | Full event payload |
| repo_name | TEXT | Repository name |
| actor | TEXT | Event actor |
| url | TEXT | Event URL |
| received_at | TIMESTAMP | Received timestamp |

### trending_cache
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PK | Primary key |
| language | TEXT | Programming language |
| since | TEXT | daily / weekly / monthly |
| repo_id | TEXT | Repository identifier |
| repo_full_name | TEXT | Full repository name |
| data | TEXT (JSON) | Full data payload |
| fetched_at | TIMESTAMP | Fetch timestamp |

### star_snapshots
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PK | Primary key |
| repo_full_name | TEXT | Repository name |
| star_count | INTEGER | Star count |
| recorded_at | TIMESTAMP | Recording timestamp |

### bookmarks
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PK | Primary key |
| repo_full_name | TEXT UNIQUE | Repository name |
| repo_url | TEXT | Repository URL |
| description | TEXT | Description |
| language | TEXT | Language |
| stars | INTEGER | Star count |
| note | TEXT | Personal note |
| saved_at | TIMESTAMP | Save timestamp |

### search_history
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PK | Primary key |
| query | TEXT | Search query |
| searched_at | TIMESTAMP | Search timestamp |

---

## 🛡️ Fault Tolerance

| Scenario | Handling |
|----------|----------|
| **API Rate Limit** | Check `X-RateLimit-Remaining`; orange warning at < 50, pause polling at < 20 |
| **Network Timeout** | `timeout=15s`, auto-retry 3 times with exponential backoff (1.5x) |
| **Invalid Token** | Clear 401 error message with guidance |
| **Scraper Failure** | Auto-fallback to backup API when HTML parsing returns empty |
| **Socket Disconnect** | Client auto-reconnects with exponential backoff (1s → 30s), shows reconnection status |
| **Database Error** | All operations wrapped in try-except, logged, with user-friendly messages |
| **Event Cleanup** | Auto-purge events older than 30 days every 50 inserts to prevent DB bloat |
| **Empty Chart Data** | Shows "Data collecting (X/7 days recorded)" instead of crashing |
| **Invalid Monitor Target** | API validation before adding; 404 targets are rejected |

---

## 🧰 Tech Stack

| Component | Technology |
|-----------|-----------|
| GUI Framework | PyQt6 |
| Network | TCP Socket (JSON protocol) |
| Database | SQLite (WAL mode, thread-safe) |
| Web Scraping | BeautifulSoup4 |
| HTTP Client | Requests (retry adapter, connection pooling) |
| Charts | matplotlib (dark theme) |
| Logging | RotatingFileHandler (5MB × 3) |
| Packaging | PyInstaller (optional) |

---

## 🤝 Contributing

Contributions are welcome! Here's how to get started:

1. Fork the repository
2. Create a new branch: `git checkout -b feature/your-feature-name`
3. Make your changes
4. Run the application and verify it works
5. Submit a Pull Request

### Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/DevRadar-GitHub-Trending-Monitor.git
cd DevRadar-GitHub-Trending-Monitor

# Install dev dependencies
pip install -r requirements.txt

# Run in development mode
python run.py
```

---

## 📦 Packaging as EXE

```bash
pip install pyinstaller
pyinstaller --onefile --windowed run.py --name DevRadar
```

Make sure `data/` directory is placed alongside the executable.

---

## ❓ FAQ

**Q: Can't connect to server after launch?**
A: Check if port 9669 is in use. If so, change `socket_port` in `data/config.json` and restart.

**Q: Search returns no results?**
A: The search API needs network access. Check the status bar for remaining API calls. If 0, you've hit the rate limit.

**Q: Trending data is empty?**
A: The scraper fetches from the GitHub Trending page. If the page changes, the system automatically falls back to a backup API.

**Q: Too many notifications?**
A: Go to `Tools → Settings` and uncheck "Enable notifications".

**Q: Where is the database file?**
A: `data/devradar.db`. Deleting it will lose all monitors and bookmarks; the system will recreate it automatically.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

Built with ❤️ using Python, PyQt6, and the GitHub REST API.

*DevRadar — Your personal window into the open-source universe.*