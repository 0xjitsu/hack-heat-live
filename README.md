# Hack Heat Live

Hack Heat is a weekly Southeast Asia hackathon and bounty board. Hack Heat Live serves that board with live countdowns: what closes this week, what is open to the Philippines and Singapore, and what pays over $10k. Every hit has a live countdown. The same answers are a web page, an HTTP API, and an MCP server that GitLab Duo can call.

**Path A, Start Fresh. Autonomy: Supervised.** A Duo flow reviews a new row and a person approves the outcome. The flow does not merge, and it does not deploy.

MIT licensed. The board needs no API keys. The optional [bounty jar](#bounty-jar-paypal-sandbox) uses PayPal sandbox keys.

## Judge path, under five minutes

```bash
git clone https://github.com/0xjitsu/hack-heat-live.git
cd hack-heat-live
python3 -m unittest discover -s tests -v
python3 -m hackheat.http_api
```

Python 3.11 or newer. No `pip install`. The server listens on `0.0.0.0:8080`.

Second terminal:

```bash
curl -s http://127.0.0.1:8080/api/query \
  -H 'content-type: application/json' \
  -d '{"question":"what hackathons close this week?"}'
```

Open http://127.0.0.1:8080 and use the three chips. The MCP test spawns the stdio server and asks the same question. It is `tests/test_mcp.py`.

To replay the week of 25 Oct 2026 after those deadlines have passed:

```bash
export HACKHEAT_NOW=2026-10-25T03:34:00+00:00
```

## The problem

Builders in the Philippines, Singapore, and the rest of SEA hear about hackathons after the useful deadline, or spend the application on a call that is on-site only or closed to their country. The dates live on Devpost, DoraHacks, FilmFreeway, and organizer pages. Hack Heat already tracks them as one board. The board is only useful if "this week" is a countdown, and if a new row is checked before it is published.

## What it does

The seed file is `data/opportunities.json`, 64 rows, updated 23 Oct 2026. "This week" means the next 7 days from the moment you ask, on a fixed Asia/Singapore offset (UTC+8). A row can have a registration close and a submission close. The countdown uses whichever future gate comes first.

| Question | What you get |
|---|---|
| `what hackathons close this week?` | Hackathons and challenges with a gate in the next 7 days, soonest first |
| `which ones are open to PH/SG?` | Remote calls whose notes do not exclude PH or SG. "Check the rules" stays in a side list |
| `which have prizes over $10k?` | Open calls with a USD prize strictly above 10000 |

PH/SG handling follows the row text. Where a row says it uses the standard Devpost exclusion list, the Philippines and Singapore count as open, because they are not on that list. An on-site-only row does not.

## Duo Agent Platform

Three pieces, all in the repo:

1. **MCP client.** `.gitlab/duo/mcp.json` starts this server over stdio and pre-approves `query_board`, `list_closing`, `list_eligible`, `list_by_prize`, `get_opportunity`, `board_status`, and the bounty jar tools `jar_status`, `create_bounty_order`, `capture_bounty_order`. Pre-approving the order tool is safe because it only returns a PayPal approval link; a person still approves the payment. Duo CLI and the IDE extension load that file. `POST /mcp` speaks the same JSON-RPC for a remote client after Cloud Run.
2. **Custom flow.** `flows/radar-curator.yml` is flow-registry v1. Paste it into **AI → Flows**. `curator_agent` runs `python3 -m hackheat.curator validate` on the candidate in the merge request. `outcome_gate` is one `HumanInputComponent` (Approve / Modify / Reject). `publisher_agent` runs only after Approve, posts the review, and applies the row with `--approved-by`. Per-tool approval is off. One human decision is the Supervised level. Assisted would have stopped on every tool. Hands-off would have merged and deployed with nobody watching.
3. **Flow execution config.** `.gitlab/duo/agent-config.yml` makes `python3` resolve in GitLab's default flow image, so the curator can run the validator. GitLab reads it from the default branch only.
4. **Custom agent.** `agents/radar-curator.yml` is the chat/IDE agent. Custom flows do not call a catalog agent. They carry their own prompts. The agent exists so Duo Chat can ask the board through MCP without starting the write flow.

Import, enablement, and the mention to type are in [docs/GITLAB_IMPORT.md](docs/GITLAB_IMPORT.md).

Try the gate locally, with no GitLab account:

```bash
python3 -m hackheat.curator validate candidates/example-good.json
python3 -m hackheat.curator validate candidates/example-stale.json
```

The good sample is valid and still does not touch `data/opportunities.json`. The stale sample is rejected. Applying is a separate command and it exits if `--approved-by` is missing.

## Lifecycle

| Stage | Where it shows up |
|---|---|
| Plan | The flow reads the MR and the candidate before anyone edits the board |
| Create | After approval, the publisher writes the normalized row and the MR note |
| Verify | `lint` and `unittest`, including the MCP "closing this week" test and the flow-file checks |
| Package | `python -m hackheat.ci package` builds `dist/hack-heat-live-0.1.0.zip`. `Dockerfile` builds the image |
| Secure | GitLab SAST and Secret Detection templates run in the `secure` stage, and `python -m hackheat.ci secrets` fails the pipeline on private keys and common token prefixes |
| Release | Pushing a tag such as `v0.1.0` runs the `release` job, which creates a GitLab Release. The zip artifact is the bundle. Nothing is tagged automatically |
| Configure | `deploy/cloudrun/service.yaml` and the Dockerfile. Port 8080, scale to zero |
| Monitor | `freshness` CI job and `GET /api/freshness` report open rows and the next gate |
| Govern | The outcome gate, plus a manual `deploy_production` job. A person merges the MR |

## API

| Method | Path | Body or query |
|---|---|---|
| GET | `/` | `?q=` renders the page |
| GET | `/api/health` | |
| GET | `/api/freshness` | Next open gate |
| GET or POST | `/api/query` | `q` or `{"question":"..."}` |
| GET | `/api/opportunities` | `window=this_week`, `region=PH/SG`, `min_prize=10000` (inclusive; `prize_op=gt` for a strict cut), `format=hackathon` |
| GET | `/api/opportunities/<id>` | |
| POST | `/mcp` | One JSON-RPC message |

Stdio MCP, for Duo and any other client:

```bash
python3 -m hackheat.mcp_server
```

Messages are one JSON object per line. Logs go to stderr.

## Bounty jar (PayPal sandbox)

Every radar card has a bounty jar: the sandbox total pledged to that hackathon, and `+$1`, `+$5`, `+$10` buttons. A button opens PayPal Checkout (JS SDK). The server creates the order with Orders v2 and captures it after the payer approves. A pledge counts only when the capture comes back `COMPLETED` for the same board row. Capturing the same order twice does not count it twice.

The AI side is the MCP server. An agent (GitLab Duo, Claude, any MCP client) can ask *"which hackathons closing this week have the biggest jars?"* (`jar_status`), then add to one (`create_bounty_order`). That returns a PayPal approval link for a person to open. No money moves until a person approves, and `capture_bounty_order` books it.

| Method | Path | Body |
|---|---|---|
| GET | `/api/bounty/<id>` | Jar total, pledge count, whether keys are configured |
| POST | `/api/bounty/<id>/order` | `{"amount": 1 \| 5 \| 10}` → `{id, approveUrl}` |
| POST | `/api/bounty/<id>/capture` | `{"orderID": "..."}` → jar after capture |

**Without keys** the app runs exactly as before. Each card shows the jar at $0.00 with disabled buttons and "Sandbox keys not configured", the order and capture endpoints return 503, and the MCP tools return a tool error that says so.

**Set it up (judges, about 5 minutes):**

1. Sign in at [developer.paypal.com](https://developer.paypal.com) → **Apps & Credentials** → toggle **Sandbox** → **Create App** (type: Merchant). Copy the Client ID and Secret.
2. **Testing Tools → Sandbox Accounts** already has a Personal (buyer) account. Use its email and password in the PayPal popup.
3. Run locally:
   ```bash
   export PAYPAL_CLIENT_ID=...  PAYPAL_CLIENT_SECRET=...  PAYPAL_ENV=sandbox
   python3 -m hackheat.http_api
   ```
   Open http://127.0.0.1:8080, press `+$5` on a card, and pay with the sandbox buyer.
4. On Vercel: Project → Settings → Environment Variables, add the same three names (secret marked Sensitive), then redeploy.

Pledges live in `var/bounties.json` locally (gitignored). On Vercel the filesystem is ephemeral, so the jar is in memory and resets on a cold start. That is a known v0 limit, marked `TODO(bounty-jar)` in `hackheat/bounty.py`.

**Payouts.** `hackheat/payouts.py` is the seam that pays a winner from the jar. `PayPalPayout` uses the sandbox Payouts API. `NearIntentsPayout` is a stub that raises `NotImplementedError`. It marks where a NEAR Intents settlement goes for the NEAR hackathon. Nothing calls a payout automatically; a person decides who won.

**Why not `paypal-agent-toolkit`?** Version 1.11.0 hard-pins `langchain`, `crewai-tools`, and `openai-agents`. This repo runs with no `pip install`, so `hackheat/paypal.py` calls the same REST endpoints with `urllib`: OAuth client credentials, Orders v2 create and capture, Payouts. The bounty tools ship in this repo's own MCP server instead.

## Vercel

`api/index.py` wraps the same `Handler` the Docker image runs, and `vercel.json` rewrites every path to it. The Cloud Run path is unchanged.

```bash
vercel deploy        # preview
```

## Configuration

Copy `.env.example` if you want a reminder. The process reads the environment. The only secret is the optional PayPal sandbox client secret.

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8080` | HTTP port |
| `HACKHEAT_HOST` | `0.0.0.0` | Bind address |
| `HACKHEAT_NOW` | current time | Freeze the clock, ISO 8601 |
| `HACKHEAT_BOARD` | `data/opportunities.json` | Board file |
| `PAYPAL_CLIENT_ID` | unset | PayPal sandbox REST app client id. Public, it goes into the page for the JS SDK |
| `PAYPAL_CLIENT_SECRET` | unset | PayPal sandbox secret. Server only, never logged or rendered |
| `PAYPAL_ENV` | `sandbox` | Anything other than `sandbox` turns the jar off. v0 never touches live PayPal |
| `HACKHEAT_BOUNTY_STORE` | `var/bounties.json` | Pledge file. `:memory:` keeps it in RAM. On Vercel it is always in RAM |

## Tests and CI

```bash
python3 -m unittest discover -s tests -v
python3 -m hackheat.ci lint
python3 -m hackheat.ci secrets
python3 -m hackheat.ci package
python3 -m hackheat.ci freshness
```

`.gitlab-ci.yml` is the pipeline GitLab will show after import. `.github/workflows/ci.yml` is the same checks on GitHub. `deploy_production` in GitLab is manual and allowed to stay unplayed.

## Google Cloud

[deploy/cloudrun/README.md](deploy/cloudrun/README.md) has the `gcloud` command and the Knative service. Building the image does not need a GCP login. The live URL is the only part that needs a project, and it is optional.

## Sustainability

[docs/SCI.md](docs/SCI.md) is an SCI estimate: the hot path is a CPU filter with no model call, and Cloud Run scales to zero. The number is an estimate from stated assumptions, using the 2022 Singapore grid factor as a placeholder for the latest EMA figure.

## Submission notes

Paste-ready Devpost fields: [docs/DEVPOST.md](docs/DEVPOST.md).

Demo script, with timestamps and no copyrighted music: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

Nothing in this repo registers or submits the hackathon entry.
