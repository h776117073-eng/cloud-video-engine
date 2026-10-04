# Cloud Video Engine

A Node.js/Express API for deterministic motion graphics (Remotion + React) and basic video editing (FFmpeg). It does not generate video with AI models.

## Endpoints
- `GET /health` — health check.
- `POST /api/v1/render` — renders a motion design or joins/edits clips and uploads the MP4 to Supabase Storage.

The render endpoint requires `Authorization: Bearer <API_KEY>`. Configure a strong random API_KEY; requests are rejected if it is unset.

## ChatGPT custom connection (MCP)

The service exposes a stateless Streamable HTTP MCP endpoint at `POST /mcp`.
Configure the custom connection with this endpoint:

`https://cloud-video-engine.onrender.com/mcp`

Authentication: HTTP Bearer token using the same value configured as Render's `API_KEY`.
Do not paste the token into source files, GitHub, or chat messages. After connecting, scan tools; the server exposes `cloud_video_health` and `render_video`.

The MCP endpoint currently uses bearer-token authentication, not OAuth. It returns JSON-RPC responses over Streamable HTTP and does not provide an SSE stream. The custom MCP connection feature is available only on supported ChatGPT plans/workspaces; if the app creation screen is unavailable, check your plan and developer-mode/workspace permissions.

## Setup
1. Create a Supabase project and a Storage bucket named `video-renders`. For the current implementation, make the bucket public so returned video URLs are accessible. Do not expose the service-role key.
2. Push this repository to GitHub.
3. In Render, create a Web Service from this repository and select Docker.
4. Set environment variables: `API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and optionally `SUPABASE_STORAGE_BUCKET` and `RENDER_CONCURRENCY`.
5. Deploy and test `/health`.
6. Replace the placeholder server URL in `openapi.json` with the actual Render hostname, then import the file in Custom GPT → Configure → Actions. Set HTTP Bearer authentication to the same API_KEY.

## Motion example
```json
{"projectType":"motion","motionProps":{"titles":["Your Brand","A better way to work"],"primaryColor":"#6C5CE7","durationSeconds":8,"animationStyle":"slide","subtitle":"A short tagline","width":1920,"height":1080,"fps":30}}
```

## Edit example
```json
{"projectType":"edit","editProps":{"clips":[{"url":"https://public.example/clip1.mp4","startSeconds":0,"endSeconds":7},{"url":"https://public.example/clip2.mp4","startSeconds":2,"endSeconds":10}],"audioUrl":"https://public.example/music.mp3","audioVolume":0.35,"outputWidth":1920,"outputHeight":1080,"fps":30}}
```

## Local Docker
```bash
cp .env.example .env
# Fill in real credentials; never commit .env
docker build -t cloud-video-engine .
docker run --rm -p 10000:10000 --env-file .env cloud-video-engine
curl http://localhost:10000/health
```

## Limitations and security
- Rendering is synchronous and CPU/RAM intensive; hosting plans can time out or sleep. Test short clips on the actual service plan.
- Public bucket URLs are accessible to anyone with the link. Use signed URLs if output is sensitive.
- HTTPS and redirect blocking alone are not complete SSRF protection. Before exposing this API to untrusted users, add DNS/IP allowlisting and robust job limits.
- Only compatible source media will concatenate reliably. Test your media formats.
- Review Remotion's current licensing for your intended use.


# Blender Cloud Rendering Agent

This repository now contains an automated headless Blender rendering pipeline driven by natural-language prompts.

## Architecture

- `.github/workflows/blender_render.yml` — Ubuntu GitHub-hosted runner, Blender 5.2.2 LTS installation/cache, headless render, MP4 validation, artifact upload.
- `tools/agent.py` — natural-language AI agent. Calls the OpenAI Responses API, generates a bpy script, validates it, Base64-encodes it, dispatches the workflow, polls the run, and returns the artifact URL.
- `tools/render_dispatch.py` — GitHub REST Actions client for workflow dispatch, run polling, and artifact lookup.
- `tools/AGENT_SYSTEM_PROMPT.md` — Blender runtime contract and bpy generation rules.
- `tools/agent_tools.json` — function/tool schema for an agent framework.
- `tools/examples/ai_studio.py` — complete 5-second AI STUDIO cinematic test scene.
- `inputs/` and `outputs/` — local/project media directories.

## GitHub Actions contract

The workflow supports `workflow_dispatch` inputs:

- `script_path` — repository-relative Python script path.
- `script_base64` — Base64-encoded Python script. Exactly one of `script_path` or `script_base64` must be supplied.
- `output_name` — simple MP4 filename.
- `blender_version` — Blender Linux x64 release. The current pinned production default is 5.2.2 LTS.

The runner executes Blender in background mode and sets `BLENDER_OUTPUT` to the required final path. The rendered file is uploaded as an Actions artifact with a 3-day retention period.

## Agent setup

Create a GitHub fine-grained token with Actions read/write permission for this repository and export it without committing it:

    export GITHUB_TOKEN="..."

Create an OpenAI API key and export it:

    export OPENAI_API_KEY="..."

Install the small agent dependency set:

    python3 -m pip install -r tools/requirements.txt

Run an end-to-end render:

    python3 tools/agent.py "Create a 5-second cinematic 3D video with a glowing gold title AI STUDIO and a smooth camera orbit."

The command prints JSON containing the generated script metadata and the GitHub artifact download URL.

Generate without dispatching:

    python3 tools/agent.py --no-dispatch --save-script outputs/generated.py "Create a 5-second cinematic 3D title."

The OpenAI API model defaults to `gpt-5.6` and can be changed with `OPENAI_MODEL` or `--model`.

## Manual REST dispatch

The GitHub endpoint is:

    POST https://api.github.com/repos/h776117073-eng/cloud-video-engine/actions/workflows/blender_render.yml/dispatches

The request body follows:

    {
      "ref": "main",
      "inputs": {
        "script_base64": "<BASE64_SCRIPT>",
        "output_name": "render.mp4",
        "blender_version": "5.2.2"
      }
    }

The dispatcher uses the current GitHub API version header and then polls the workflow run until it reaches `completed`. After success it locates the `blender-render-<run_id>` artifact.

## Cost model

GitHub's current billing documentation states that standard GitHub-hosted runners are free for public repositories; private repositories use the included quota for the account plan and can incur charges after the quota is exceeded. Artifact and cache storage are also subject to plan limits. This project intentionally uses a standard Ubuntu runner and a short artifact retention period.

## Security

Do not put `GITHUB_TOKEN`, `OPENAI_API_KEY`, Supabase service-role keys, or other credentials in source files. Generated Blender code is statically checked for prohibited network/process execution before the workflow is dispatched.

The GitHub artifact download URL is a GitHub API artifact archive URL. It downloads a ZIP archive containing the MP4 rather than exposing the raw MP4 as a permanent public URL.
