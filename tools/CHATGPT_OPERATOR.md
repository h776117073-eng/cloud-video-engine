# ChatGPT Direct Blender Operator

This project is designed to be operated directly from ChatGPT through the connected GitHub account.

## Control loop

1. ChatGPT receives the user's natural-language editing/rendering request.
2. ChatGPT writes or updates `render_requests/current.py` in this repository.
3. A single GitHub commit to that file automatically triggers `.github/workflows/blender_render.yml`.
4. The Ubuntu GitHub-hosted runner installs or restores the pinned Blender release, runs Blender headlessly, validates the MP4, and uploads it as a GitHub Actions artifact.
5. ChatGPT monitors the workflow run through GitHub, inspects jobs/logs when necessary, downloads the artifact when successful, and reports the final result.

No OpenAI API key is required by the repository. No separate AI-agent service is required. The model generating the Blender code is ChatGPT in the conversation.

## Render request contract

`render_requests/current.py` is both the Blender script and the request metadata carrier. The first two lines must be:

    # OUTPUT_NAME: render.mp4
    # BLENDER_VERSION: 5.2.2

The remainder must be a self-contained `bpy` script that reads:

    import os
    output_path = os.environ.get("BLENDER_OUTPUT", "//render.mp4")

and assigns:

    scene.render.filepath = output_path

The script must configure the output explicitly for FFmpeg/H.264 MP4.

## Security

The repository does not store GitHub, OpenAI, Render, or Supabase secrets for this control loop. ChatGPT's connected GitHub integration is the only control-plane credential.

Generated Blender scripts are constrained to Blender/Python APIs and are reviewed for dangerous process/network primitives before dispatch. The workflow does not grant repository write permissions to the render job.

## Future requests

For every new user command, ChatGPT should replace `render_requests/current.py` in one commit. That commit is the trigger. Do not use the browser and do not ask the user to manually press Run workflow.

