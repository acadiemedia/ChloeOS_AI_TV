# ChloeOS_AI_TV

This repository serves as the master hub for the Chloe AI TV project, orchestrating content generation, OBS Studio automation, and live streaming.

## Architecture Overview

### 1. Core Layout

*   **Master device (phone / Termux):**
    *   Runs Codex CLI + Google CLI
    *   Controls GitHub commits/pulls
    *   Sends commands via REST or SSH to desktop OBS

*   **Desktop (broadcast node):**
    *   OBS Studio + WebSocket plugin enabled
    *   Folder synced to GitHub (`/scripts/obs/`)
    *   Auto-pulls latest scripts from main branch

*   **GitHub (cloud relay):**
    *   Stores code + OBS Lua/Python automations
    *   GitHub Actions optionally trigger remote updates
    *   Mirror to `cdn.acadiemedia.com` for assets

*   **LLMs:**
    *   Codex → OpenAI backend (code generation)
    *   Gemini → Google backend (cross-checks + enrichment)

### 2. Data Flow

`[Phone CLI] ⇄ [GitHub Repo] ⇄ [Desktop OBS Node]`
       `↓`
   `(LLMs for content)`

**Cycle:**

1.  You type in Termux → Codex writes a script.
2.  Script is auto-committed and pushed to GitHub.
3.  Desktop OBS auto-pulls new commits every few minutes.
4.  Lua/Python scripts update live scene automation or add new AI TV segments.
5.  ChloeOS AI TV runs with the latest creative logic.

### 3. Tools You’ll Need

**On phone (Termux):**

```bash
pkg install git python nodejs
pip install requests
npm install -g @google/clasp
```

Then:

```bash
codex login
gh auth login
```

**On PC:**

*   Install OBS WebSocket (v5+)
*   `git clone` this repository
*   Add a small watcher script:

```bash
watch -n 120 'git pull && echo "OBS Scripts Updated"'
```

### 4. Optional Automation

To make it self-syncing:

*   Add a GitHub Action that pushes a webhook to OBS node.
*   The OBS node runs `pull_and_reload.sh`:

```bash
git pull
obs-cli scene switch "AI_TV"
```

Once Codex and Gemini are both authenticated, you’ll have a dual LLM relay — OpenAI + Google — feeding your TV scripts and publishing them automatically.

### 5. Content Structure

The `content/` directory within this repository serves as the central hub for all content and visual assets related to Chloe AI TV. This content is organized to support a continuous cycle between a noon educational pulse and a midnight adult pulse.

*   **`content/scripts/`**: Contains all generated and curated scripts for AI talk shows, animated segments, human reflection sessions, and any other narrative content.
*   **`content/visuals/`**: Stores visual assets, including animated character models, background art, scene compositions, and any other graphical elements used in the stream. Visuals can be generated on-device or remotely and are synced here.
*   **`content/audio/`**: Holds audio files such as voiceovers, sound effects, background music, and any other auditory components.
*   **`content/submissions/`**: This directory is designated for open submissions from external sources. At the end of each 12-hour cycle, AI will process and merge content from this directory into the next storyline.
*   **`content/metadata/`**: Contains metadata files, scheduling information, content tags, and other administrative data crucial for the autonomous operation and content rotation of Chloe TV.
