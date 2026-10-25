# Demo video script

Under three minutes. Record the screen with a microphone. Use no music, or a track you know is royalty-free and that you have the right to use. Do not use a commercial song. Do not show third-party logos. Opportunity names are fine as text on the Hack Heat page, because they are the board. If you freeze the clock, set it before the first shot:

```bash
export HACKHEAT_NOW=2026-10-25T03:34:00+00:00
```

Leave the variable unset if you record while the deadlines are still in the future. The GitLab row closes Tue 27 Oct 2026, 21:00 SGT.

Target length: about 2 minutes 40 seconds.

## 0:00–0:18 — The problem

**Shot:** A blank terminal, then the Hack Heat homepage. No intro card with logos.

**Voiceover:** Hackathon deadlines in Southeast Asia are spread across a dozen sites. Hack Heat is the weekly board. Hack Heat Live lets a person, or an agent, ask what closes this week, what is open to the Philippines and Singapore, and what pays over ten thousand dollars. The answers carry a live countdown.

## 0:18–0:48 — Three questions

**Shot:** The browser on the homepage. Click "Closing this week", then "Open to PH/SG", then "Prizes over $10k". Pause on the GitLab row so the countdown is readable. Scroll one card so the prize and the PH/SG line are visible.

**Voiceover:** This is the seeded board, sixty-four real rows. This week means the next seven days, on the Singapore clock. Life After Code is still open. The page says when registration or submission closes, and whether a remote applicant in the Philippines or Singapore is blocked.

## 0:48–1:15 — MCP, the same answer

**Shot:** Split or cut to a terminal. Run the curl command below. Select the line that contains `gitlab-life-after-code` and the words "closes in".

```bash
curl -s http://127.0.0.1:8080/api/query \
  -H 'content-type: application/json' \
  -d '{"question":"what hackathons close this week?"}'
```

**Voiceover:** The same question over HTTP. The MCP server speaks this to GitLab Duo. The repo registers it in `.gitlab/duo/mcp.json`, so Duo Agent Platform can call the board as an MCP client. No key, no account.

## 1:15–2:05 — Supervised curator

**Shot:** Terminal. Run the validator on the good sample, then on the stale sample. Then show `flows/radar-curator.yml` scrolled to `HumanInputComponent` and the approve, modify, and reject routes. If the GitLab project is already imported, cut to the flow run and the Approve button. If it is not, stay on the YAML and say the gate is what you click after import.

```bash
python3 -m hackheat.curator validate candidates/example-good.json
python3 -m hackheat.curator validate candidates/example-stale.json
```

**Voiceover:** New rows do not land on the board by themselves. The radar-curator flow reads the merge request, runs this validator, and checks the deadline and eligibility. This sample is valid, and it still will not write anything until a person approves. The stale sample is rejected because the date has passed. In GitLab that approval is one gate, not a prompt on every tool call. That is Supervised autonomy. After approval the publisher posts the review. Merging, and the Cloud Run deploy, stay manual.

## 2:05–2:28 — Pipeline

**Shot:** The GitLab pipeline page, or the GitHub Actions run if the import is not done yet. Point at lint, test, secure, build, and the freshness job. Point at the manual `deploy_production` job without clicking it, or click it only if you are ready to say it prints the deploy command and does not ship.

**Voiceover:** The pipeline lints, tests, scans for secrets, packages the service, and checks that deadlines still parse. Production deploy is a manual job. The Cloud Run spec is in the repo and scales to zero. Path A, Supervised. The human approves the outcome.

## 2:28–2:40 — Close

**Shot:** Back to the homepage, the closing-this-week list, countdown visible. Hold. No end card, no music sting.

**Voiceover:** Hack Heat Live is the weekly board, live, and reviewable. Ask it what closes. A person still decides what gets added.

## Shot list

| Time | Picture | Audio |
|---|---|---|
| 0:00–0:18 | Homepage, no logos | Problem and the three questions |
| 0:18–0:48 | Click the three chips, hold the GitLab countdown | What "this week" and PH/SG mean |
| 0:48–1:15 | curl the JSON API | MCP and Duo as a client |
| 1:15–2:05 | Validator output, then the flow YAML or the live gate | Supervised approval |
| 2:05–2:28 | Pipeline jobs, manual deploy left unplayed or explained | CI and Cloud Run |
| 2:28–2:40 | Homepage countdown | One-line close |

## Before you upload

- The video is under 3:00.
- It is public on YouTube.
- There is no copyrighted music and no third-party logo.
- The automation is visible: the query result, the validator, and the pipeline or the flow gate.
