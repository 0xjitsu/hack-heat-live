# Devpost fields

Paste these into the submission form. They describe a Path A, Supervised project. Do not tick Path B.

## Title

Hack Heat Live

## Tagline

A weekly Southeast Asia hackathon radar with live countdowns, an MCP server, and a supervised GitLab Duo curator.

## Inspiration

Hackathon dates for Southeast Asia are scattered across Devpost, DoraHacks, FilmFreeway, and organizer sites. A weekly board goes stale the moment a deadline moves, and "does this close before Friday, and can someone in Manila or Singapore actually enter?" takes another pass through the rules. We already keep that board. Hack Heat Live makes the same 64 rows answerable, with the clock running, and puts new rows through a supervised review instead of a silent edit.

## What it does

Hack Heat Live serves the weekly board over a small web page, an HTTP API, and a Model Context Protocol server. People and agents can ask:

- What hackathons close this week?
- Which ones are open to PH/SG?
- Which have prizes over $10k?

"This week" means the next 7 days. Every hit includes a live countdown in Asia/Singapore. The next gate is registration when that is the sooner deadline, and submission when registration has already shut.

A radar-curator flow on the GitLab Duo Agent Platform reviews a candidate row in a merge request. It checks the deadline, the prize, and PH/SG eligibility by running the same validator the tests run. It stops at an approval gate. A person approves the outcome, and only then does a publisher post the review and update the board. The merge, and the optional Cloud Run deploy, stay manual.

## How we built it

Python 3.12, standard library only. The board is the real 64-row JSON file. The MCP server speaks newline-delimited JSON-RPC on stdio and the same messages on `POST /mcp`. GitLab Duo reads `.gitlab/duo/mcp.json` and can call the six board tools. The custom flow in `flows/radar-curator.yml` is flow-registry v1: a curator agent, a `HumanInputComponent` approval gate, and a publisher agent. That single gate is the Supervised autonomy level. Per-tool approval is off, so the human is not in the loop for every read.

GitLab CI and GitHub Actions both lint, test, secret-scan, package a zip, check the Cloud Run files, and run a deadline-freshness job. `deploy_production` is a manual job.

## Challenges

Rows often have two clocks, registration and submission, and some dates have no time. Date-only values use end of day UTC, which is the board's own rule. "Open to PH/SG" is not a column. The eligibility check reads the row's notes and treats the standard Devpost exclusion list as allowing the Philippines and Singapore, because those places are not on the list in the hackathon rules. Calls that say "check the rules" stay in a separate bucket.

The other hard part was autonomy. Approving every tool call would have made this Assisted. Letting the publisher merge and deploy would have pretended to be Hands-off. The flow reviews on its own, then waits once, for the outcome.

## Accomplishments

- The seeded board answers the three questions with countdowns, including over HTTP and over MCP. A test drives the stdio server and checks a "closing this week" reply.
- The curator refuses a past deadline and refuses to write the board until `--approved-by` is set.
- The repo carries an MIT license, a GitLab CI pipeline, a GitHub Actions pipeline, a paste-ready Duo flow and agent, and a Cloud Run service that scales to zero.
- An SCI note estimates the carbon of one query against a manual pass and against an always-on instance.

## What's next

Register the flow in the provisioned GitLab project, record the three-minute demo, and deploy the Cloud Run service if we want the Google Cloud bonus. After that, a scheduled trigger can open a weekly freshness issue when the board file is older than the newest deadline it still lists.

## Built with

- Python 3.12
- Model Context Protocol (stdio and HTTP)
- GitLab Duo Agent Platform (custom flow, custom agent, MCP client)
- GitLab CI/CD
- GitHub Actions
- Docker
- Google Cloud Run

## Path and autonomy

- Path: A, Start Fresh
- Autonomy: Supervised
- Google Cloud bonus: deployment code is in `deploy/cloudrun/`. Add the live URL on the form only after the service is public.
- Environment prize: opt in only if you want to. Paste the summary from `docs/SCI.md`.
