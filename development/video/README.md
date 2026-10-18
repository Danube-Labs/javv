# The triage videos

This folder makes the six videos of Use JAVV, the user section of the docs site
(`docs/use/`). A recorder takes a sharp screenshot of each state of the app, with the position
of each control. Remotion then makes all the motion over the screenshots: the camera, the
spotlight, the pointer, the clicks and the captions.

| Part | What it does |
|---|---|
| `record/` | One walk for each video (`walk-v1.mjs` to `walk-v6.mjs`) and the shared recorder (`common.mjs`). A walk signs in as `lead` and goes through the app. It writes 2x screenshots and `shots.json` to `public/vN/`. |
| `src/engine.tsx` | The engine. It calculates the timing and the camera from a list of beats. It draws the window, the spotlight, the pointer, the caption and the title cards. |
| `src/videos/` | One list of beats for each video. A beat names a screenshot, a caption, the control to show, and the control to click. |
| `stack/` | The video stack: its own store, backend and app, with made-up data. |
| `record.sh` | Starts the video stack and runs the six walks in their order. |
| `render.sh` | Renders the videos and encodes them for the docs site into `docs/use/videos/`. |

## What you need

- Docker, uv, Node.js, ffmpeg and yq.
- The frontend packages (`npm ci` in `frontend/`) and the Playwright browser. The recorder uses
  them, and the video stack serves the built app.
- A Remotion license, if it applies to you. Remotion is free for an individual and for a company
  with up to 3 employees. A larger for-profit company needs a company license.

## Make the videos again

1. Record the screenshots. This takes about 15 minutes:

    ```bash
    development/video/record.sh
    ```

2. Render and encode the videos. With no argument, all six. With numbers, only those videos:

    ```bash
    development/video/render.sh
    development/video/render.sh 3 5
    ```

3. Watch each video in `docs/use/videos/`. Then run the docs site test. It keeps each video
   under the size limit:

    ```bash
    cd backend && JAVV_OPENSEARCH_URL=http://localhost:9202 uv run pytest tests/test_docs_site.py
    ```

4. Stop the video stack. This also removes its store:

    ```bash
    development/video/stack/stop.sh
    ```

To see a video frame by frame before you render it, run `npx remotion studio src/index.ts` in
this folder.

## The video stack

| Part | Where |
|---|---|
| Store | The container `javv-os-video`, on `127.0.0.1:9203`, with the OpenSearch version from `versions.yaml` |
| Backend | `127.0.0.1:8010`, log in `out/backend.log` |
| App | `127.0.0.1:8091`, the built frontend |
| Users | `admin`, and `lead` with the security lead role |
| Passwords | One 600 file each in `sec/`. Each start makes new passwords. No script prints them. |
| Data | Two made-up clusters from `development/scripts/replay_waves.py`: `prod-eu-1` and `staging-eu` |

The ports are not the ports of the dev stack, so a recording never changes the dev store.

The walks change triage data, so `record.sh` runs them in this order on one store: walk 2 sets a
state, walk 3 accepts a risk and revokes it, walk 4 makes a bulk change, and walk 6 shows the
history of all three. For walk 5, the scanners of `staging-eu` stay silent. Short timers for
that cluster and a sweep then mark its findings Stale.

## Change a video

- To change a caption, edit the `caption` of the beat in `src/videos/`. Write it in Simplified
  Technical English. Then change the same step on the page in `docs/use/`.
- When a screen of the app changes, record again. A walk finds each control by its selector. If a
  selector changes, change it in the walk.
- A caption tells only what the screen shows.
- The engine sets the pace. A caption shows for a time that it calculates from the number of
  words. The spotlight comes after the camera move, and it goes at the click.
