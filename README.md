# Hack Heat Live

Hack Heat is a weekly Southeast Asia hackathon and bounty board. Hack Heat Live serves that board with live countdowns: what closes this week, what is open to the Philippines and Singapore, and what pays over $10k. Every hit has a live countdown. The same answers are a web page, an HTTP API, and an MCP server that GitLab Duo can call.

**Path A, Start Fresh. Autonomy: Supervised.** A Duo flow reviews a new row and a person approves the outcome. The flow does not merge, and it does not deploy.

MIT licensed. No API keys.

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

1. **MCP client.** `.gitlab/duo/mcp.json` starts this server over stdio and pre-approves `query_board`, `list_closing`, `list_eligible`, `list_by_prize`, `get_opportunity`, and `board_status`. Duo CLI and the IDE extension load that file. `POST /mcp` speaks the same JSON-RPC for a remote client after Cloud Run.
2. **Custom flow.** `flows/radar-curator.yml` is flow-registry v1. Paste it into **AI → Flows**. `curator_agent` runs `python3 -m hackheat.curator validate` on the candidate in the merge request. `outcome_gate` is one `HumanInputComponent` (Approve / Modify / Reject). `publisher_agent` runs only after Approve, posts the review, and applies the row with `--approved-by`. Per-tool approval is off. One human decision is the Supervised level. Assisted would have stopped on every tool. Hands-off would have merged and deployed with nobody watching.
3. **Custom agent.** `agents/radar-curator.yml` is the chat/IDE agent. Custom flows do not call a catalog agent. They carry their own prompts. The agent exists so Duo Chat can ask the board through MCP without starting the write flow.

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
| Secure | `python -m hackheat.ci secrets` fails the pipeline on private keys and common token prefixes |
| Release | The zip artifact is the release bundle. Production is not tagged automatically |
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

## Configuration

Copy `.env.example` if you want a reminder. The process reads the environment. There is no secret.

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8080` | HTTP port |
| `HACKHEAT_HOST` | `0.0.0.0` | Bind address |
| `HACKHEAT_NOW` | current time | Freeze the clock, ISO 8601 |
| `HACKHEAT_BOARD` | `data/opportunities.json` | Board file |

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
