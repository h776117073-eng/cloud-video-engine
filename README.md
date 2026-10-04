# Cloud Video Engine

A Node.js/Express API for deterministic motion graphics (Remotion + React) and basic video editing (FFmpeg). It does not generate video with AI models.

## Endpoints
- `GET /health` — health check.
- `POST /api/v1/render` — renders a motion design or joins/edits clips and uploads the MP4 to Supabase Storage.

The render endpoint requires `Authorization: Bearer <API_KEY>`. Configure a strong random API_KEY; requests are rejected if it is unset.

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
