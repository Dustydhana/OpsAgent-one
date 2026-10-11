# OpsAgent demo source files

Place the original screenshots in this folder. Use PNG or JPG at the highest available resolution.

Recommended sequence:

1. `01-alert-triggered.png` — Slack or Gmail monitoring alert arrives.
2. `02-agent-acknowledged.png` — OpsAgent acknowledges the alert.
3. `03-investigation-running.png` — Agent checks the server and collects evidence.
4. `04-root-cause-analysis.png` — Agent explains the likely cause and impact.
5. `05-operation-approval.png` — Proposed operation and approval screen.
6. `06-operation-complete.png` — Successful action and Slack/Gmail update.

Edit `storyboard.json` and replace each `description` with what is happening in your screenshot. Keep passwords, API keys, tokens, email addresses, public IPs, authorization messages, and other secrets out of screenshots.

Optional files:

- `voiceover.wav` or `voiceover.mp3` — narration
- `background.mp3` — licensed background music
- `logo.png` — transparent product logo

When the files are ready, ask Codex: **Create the OpsAgent demo clip from demo-source**.

