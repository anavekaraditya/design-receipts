# Capture screenshots from the running app

Capture evidence while working on a visible design decision in a runnable web app. The agent handles navigation, capture, and attachment. The designer confirms the decision through the normal decision flow.

1. Identify the route and the behavior worth showing. Reuse a known dev server for the project or start the normal local dev command from its README or manifest. Wait for the relevant UI to load and confirm you reached the right app. Keep the server running between captures. Shut down only a process you started for capture when it is no longer needed.
2. Before editing, open the page in a fresh browser context at a useful viewport. Set up the state with stable browser interactions, such as opening a menu or filling a field with dummy data. Wait for the state to be visible, then save a PNG locally in a private temporary directory. Use synthetic data and skip states that expose private information. Avoid carrying authenticated browser session state into the capture.
3. After the change, capture the same route, viewport, and interaction where that comparison still makes sense. Capture additional `state` images when an interaction introduces a distinct new screen. If the old UI is already gone or inaccessible, attach the `after` capture. Report a missing baseline without restoring or changing the checkout to reconstruct it.
4. Attach the files to the decision number, then show their links with the decision record. Keep captions concrete, such as “Next arrival is visible only on the selected stop row.” A screenshot records what rendered. Human verification and measured outcomes need their own evidence. Remove the temporary screenshot files when you have verified the attachments or abandoned the capture.

Use the host's browser when it can save a local PNG. Otherwise, use the included capture helper with Node.js 18+, an installed Playwright package, and local Chromium. It resolves Playwright from the target project or takes an explicit `--module` path to an installed package. It uses Playwright's installed Chromium or an explicit `--browser-executable` path. The helper opens a fresh browser context with loopback-only network access. If the page relies on remote assets, use the host browser to capture the complete UI.

```sh
node <skill-directory>/scripts/capture_browser.cjs \
  --url http://127.0.0.1:3000/stops \
  --output "$capture_dir/before.png" --width 1440 --height 900
```

For an interactive state, pass `--actions PATH` to a private JSON file with an array of app interactions. Use selectors drawn from the rendered page. Supported actions are `click` with `selector`, `fill` with `selector` and `value`, `press` with `selector` and `key`, and `waitFor` with `selector`.

```json
[
  {"action": "click", "selector": "button[aria-label='Open filters']"},
  {"action": "waitFor", "selector": "[role='dialog']"}
]
```

Attach each real capture to the saved decision record. Use the helper's returned `route`, or pass the browser's final path without query parameters or fragments. Use `--viewport` when you know the CSS viewport. It otherwise defaults to the PNG dimensions. Set `--date YYYY-MM-DD` if a capture was taken on a different day. The attachment is stored inside the decision log and linked from the index and compiled draft.

```sh
python3 -SB <skill-directory>/scripts/receipts.py attach-screenshot 1 "$capture_dir/before.png" \
  --state before --route /stops --viewport 1440x900 --caption "All stops show arrival predictions inline"
```

If a server, browser, or state is unavailable, finish the decision record with the available evidence and say which image is missing. Continue the normal confirmation workflow.
