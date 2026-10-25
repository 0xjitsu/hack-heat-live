# Cloud Run

Deployment is optional. Path A does not require a live URL. A public Google Cloud URL is worth up to 0.2 bonus points, and this directory is the deployment code judges look for. Nothing here needs credentials to build.

The service listens on `0.0.0.0:$PORT`. Cloud Run sets `PORT` to 8080. The service YAML scales to zero and caps the service at two instances.

## Build the image locally

```bash
docker build -t hack-heat-live .
docker run --rm -p 8080:8080 hack-heat-live
curl -s http://127.0.0.1:8080/api/health
```

## Deploy

Replace `PROJECT_ID` and run this from a machine that is already logged in to `gcloud`. This repo does not contain a key.

```bash
gcloud run deploy hack-heat-live \
  --source . \
  --project PROJECT_ID \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --port 8080 \
  --memory 256Mi \
  --min-instances 0 \
  --max-instances 2
```

`asia-southeast1` is Singapore, which matches the board's clock. After the URL exists, the same origin serves the page, `/api/query`, and `POST /mcp`.

To point GitLab Duo at the deployed MCP server, add this beside the stdio entry in `.gitlab/duo/mcp.json` once the URL is real. Do not commit the live URL if it is not public yet. A public Cloud Run URL is fine to commit when you want the bonus.

```json
{
  "mcpServers": {
    "hack-heat-live-http": {
      "type": "http",
      "url": "https://YOUR_SERVICE.asia-southeast1.run.app/mcp",
      "approvedTools": [
        "query_board",
        "list_closing",
        "list_eligible",
        "list_by_prize",
        "get_opportunity",
        "board_status"
      ]
    }
  }
}
```

## Supervised gate

`.gitlab-ci.yml` includes a manual job named `deploy_production`. The pipeline goes green without it. Playing the job checks these files and prints the `gcloud` command. It does not deploy by itself. A person runs the command above. That is the production approval for Supervised autonomy.
