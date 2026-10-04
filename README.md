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


# Direct ChatGPT Blender Rendering

The Blender renderer is controlled directly by ChatGPT through the connected GitHub account. No external AI-agent service and no OpenAI API key are required by the repository.

## Control loop

ChatGPT receives a natural-language request, writes `render_requests/current.py` in one GitHub commit, and the commit automatically starts the Blender workflow.

The workflow:

1. Checks out the repository on an Ubuntu GitHub-hosted runner.
2. Installs or restores the pinned Blender Linux x64 LTS release.
3. Reads the request script.
4. Runs Blender in background/headless mode.
5. Validates the MP4 with ffprobe.
6. Uploads the MP4 as a GitHub Actions artifact.
7. ChatGPT monitors the run, inspects logs/jobs if needed, and downloads the artifact on success.

## Request file

Every request is represented by one file:

`render_requests/current.py`

The file starts with:

    # OUTPUT_NAME: ai-studio.mp4
    # BLENDER_VERSION: 5.2.2

The remaining contents are the complete Blender `bpy` script.

The script must read the workflow output location from:

    import os
    output_path = os.environ.get("BLENDER_OUTPUT", "//render.mp4")

and set:

    scene.render.filepath = output_path

## Workflow

`.github/workflows/blender_render.yml` supports both:

- automatic rendering on a commit to `main` that changes `render_requests/current.py` (the normal direct ChatGPT path);
- manual `workflow_dispatch` with `script_path`, `script_base64`, `output_name`, and `blender_version`.

The automatic path is the normal ChatGPT control path and requires no browser interaction.

## Security model

The repository does not contain GitHub, OpenAI, Render, or Supabase secrets for Blender control. The ChatGPT GitHub integration performs the repository write that acts as the workflow trigger.

The render job has `contents: read` permission only. Generated Blender code should remain deterministic and must not use subprocesses, network clients, dynamic code execution, or credential files.

## Current Blender release

The project pins Blender **5.2.2 LTS**. Blender 5.2 LTS is an actively maintained LTS branch, and Blender lists 5.2.2 as the current 5.2 LTS update. citeturn914562search1turn914562search3

## Existing Cloud Video Engine

The original Node.js/Express API remains available at:

- `GET /health`
- `POST /api/v1/render`

The Blender workflow is independent and can later be exposed through the existing MCP service.
