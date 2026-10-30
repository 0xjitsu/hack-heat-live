# Import this repo into GitLab and turn on Duo

Do this in the provisioned hackathon project if it exists. Duo Agent Platform is enabled for the group GitLab creates after contributor approval. GitLab's docs say the Agent Platform needs a project in a **group** namespace, and on the Free tier it uses purchased GitLab Credits, so a personal project can carry the code and the pipeline history but may not run the flow. Use a personal public project only for the code and pipeline while the provisioned project is pending. The project has to be **public**. The MIT `LICENSE` file has to stay at the repo root so it shows in About.

These steps do not register or submit the Devpost entry. That stays a separate, manual action.

## 1. Create the public GitLab project from GitHub

GitHub repo: `https://github.com/0xjitsu/hack-heat-live`

1. Sign in to GitLab.
2. If the hackathon group has already provisioned a project, open that project and use it. Skip to step 2 of the mirror instructions below and push this repo into that project.
3. Otherwise: **New project → Import project → GitHub**.
4. Pick `0xjitsu/hack-heat-live`.
5. Set **Visibility** to **Public**.
6. Import.

If GitHub import is unavailable, create a public blank project and push a mirror:

```bash
git clone https://github.com/0xjitsu/hack-heat-live.git
cd hack-heat-live
git remote add gitlab https://gitlab.com/GROUP/hack-heat-live.git
git push -u gitlab main
```

To keep the mirror updated: **Settings → Repository → Mirroring repositories → Add new**. Mirror direction: pull from `https://github.com/0xjitsu/hack-heat-live.git`.

## 2. Confirm the license and the pipeline

1. Open the project. In **About**, GitLab should list **MIT License**. The file is `LICENSE` at the root. Do not rename it.
2. **Settings → General → Visibility** is Public.
3. **Build → Pipelines → Run pipeline** on `main`.
4. Wait until `lint`, `test`, `secure`, `build`, and `freshness` pass. `deploy_production` stays a manual play button. Leave it unplayed until you actually want the Cloud Run command printed. The pipeline is green without it.

Shared runners must be enabled (**Settings → CI/CD → Runners**). The jobs use the public `python:3.12-slim` image and do not need CI variables.

## 3. Turn on Duo Agent Platform

You need the Maintainer or Owner role.

1. Open the **top-level group**. **Settings → GitLab Duo → Change configuration**.
2. Turn on **GitLab Duo** / Duo Agent Platform if it is not already on for the hackathon group.
3. Under **Custom and external agents and flows**, turn on **Allow custom flows**.
4. Under **External MCP tools**, turn on **Allow external MCP tools**. Save.
5. On the project, confirm **AI → Flows** and **AI → Agents** are visible. If they are not, Duo is not on for this group yet. Use the provisioned hackathon project instead of a personal one.

## 3b. Flow execution image

`.gitlab/duo/agent-config.yml` is already in the repo. Flows run in GitLab's default flow image, which ships Python 3.12. The setup script makes sure `python3` points at it. GitLab only reads this file from the default branch, so it must be on `main` in the GitLab project before the first flow run.

## 4. Register the radar-curator flow

The flow file is paste-ready. It has no top-level `name` or `description`, because custom flows reject those fields.

1. **AI → Flows → New flow**.
2. Display name: `Radar curator`.
3. Description: `Reviews a candidate Hack Heat row, then waits for a human to approve the board update.`
4. Visibility: Public if you want judges to open it, otherwise Private.
5. Under **Configuration**, choose **Flow** and paste the entire contents of `flows/radar-curator.yml`.
6. **Create flow**.
7. Open the flow → **Enable**.
8. Project: this project.
9. Triggers. Add both if the UI allows more than one:
   - **Mention**, so a comment `@ai-radar-curator-GROUP` starts a review.
   - **Merge request → Created**, so a new candidate MR starts the flow on its own.
10. Instructions on the trigger, optional: `Review the candidate JSON in this merge request. Run the curator validator. Do not edit the board until the outcome gate is approved.`
11. Enable.

GitLab creates a service account named like `ai-radar-curator-GROUP` and gives it Developer on the project. That account is who you mention.

The flow is Supervised:

- `curator_agent` reads the MR and runs `python3 -m hackheat.curator validate`.
- `outcome_gate` is a `HumanInputComponent` with Approve, Modify, and Reject.
- `publisher_agent` runs only on Approve. It posts the MR note and runs `curator apply --approved-by`.
- It does not merge. You merge. That is the govern step.

## 5. Register the custom agent

The flow does not call this agent. Duo custom flows build their own agents from the YAML. This agent is for Duo Chat and the IDE, with the MCP tools attached.

1. **AI → Agents → New agent**.
2. Display name: `Radar curator`.
3. Description: copy the `description` from `agents/radar-curator.yml`.
4. System prompt: copy the `system_prompt` block from that file.
5. Tools: Read file, Grep, Find files, Run command, Get merge request. Names in the file are `read_file`, `grep`, `find_files`, `run_command`, `get_merge_request`.
6. If the form has MCP tools, add `query_board`, `list_closing`, `list_eligible`, `list_by_prize`, `get_opportunity`, `board_status`, `jar_status`, `create_bounty_order`.
7. Create, then enable the agent for this project.

## 6. Point Duo at the MCP server

The workspace file is already in the repo:

`.gitlab/duo/mcp.json`

It starts `python3 -m hackheat.mcp_server` over stdio and pre-approves the six board tools. Duo CLI and the GitLab IDE extension load this file from the project root.

1. Clone the project locally, or open it in the GitLab Web IDE.
2. Restart the GitLab Duo CLI or the IDE so it reloads MCP config.
3. In Duo Chat, ask: `Using hack-heat-live, what hackathons close this week?`
4. The client should call `query_board`. Approve the tool if the UI asks and `approvedTools` did not apply.

For Cloud Run later, add the HTTP block in `deploy/cloudrun/README.md`. Do that only after the service has a public URL.

## 7. Run the supervised demo on a merge request

1. Branch from `main`.
2. Add `candidates/example-good.json` if it is not already on the branch, or change a throwaway field in it so the MR has a diff.
3. Open a merge request.
4. If you used the mention trigger, comment: `@ai-radar-curator-GROUP Review the candidate JSON and validate the deadline and PH/SG eligibility.`
5. Wait for the curator summary.
6. Open the flow session (the link in the MR note, or **AI → Sessions**). On the outcome gate, click **Approve** once. Do not approve individual tool calls. There is one decision.
7. Confirm the publisher commented and, if the verdict was approve, updated `data/opportunities.json`.
8. Try `candidates/example-stale.json` in a second MR. The validator rejects it. Do not approve a write.
9. Leave the MR unmerged until you are happy with the diff. Then merge it yourself.

## 8. Optional Cloud Run bonus

Follow `deploy/cloudrun/README.md`. The manual pipeline job `deploy_production` only prints the `gcloud` command. You run that command from a logged-in shell. Put the public URL on the Devpost form. There is no cloud key in this repo.

## 9. What a judge can do without your GitLab account

From a clone, in under five minutes:

```bash
python3 -m unittest discover -s tests -v
python3 -m hackheat.http_api
```

In another terminal:

```bash
curl -s http://127.0.0.1:8080/api/query \
  -H 'content-type: application/json' \
  -d '{"question":"what hackathons close this week?"}'
```

The stdio MCP test in `tests/test_mcp.py` is the scripted version of the Duo client call.
