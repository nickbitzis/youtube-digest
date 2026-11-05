# YouTube Digest

YouTube Digest checks a list of channels each morning, summarizes every new video with Claude, and sends one push notification to your phone that says which videos are worth watching. I wanted to keep up with tech news without spending an hour a day on YouTube.

## How it works

1. **New videos.** It reads each channel's free RSS feed, so no YouTube API key is needed. The feeds fail now and then, so it retries and then falls back to the channel's Videos page.
2. **Transcripts.** It pulls captions with `youtube-transcript-api`. Videos without captions are summarized from their title and description.
3. **Summary.** One Claude API call covers the whole day's batch. It labels each video Must watch, Worth skimming or Skip, with a two to three sentence summary and a one-line reason. The `audience` text in `config.toml` tells the model what you care about. Video text is wrapped as untrusted content in the prompt, so a transcript can't give the model instructions.
4. **Notification.** It sends a push through [ntfy](https://ntfy.sh), which is free and needs no account. The title names the top pick, and long digests are split into parts.
5. **Schedule.** `ytdigest install` sets up a macOS LaunchAgent that runs daily. If the Mac is asleep at run time, the job runs when it wakes.

Days with no new videos send nothing. If a step fails, the notification says so and still lists the titles.

## Run it

Requires [uv](https://docs.astral.sh/uv/) and an Anthropic API key.

```bash
uv run ytdigest install             # installs the daily job and creates a .env to fill in
uv run ytdigest run --no-notify     # preview today's digest without sending or marking videos as seen
uv run ytdigest test-notify         # check the phone link
uv run pytest
```

The installer creates a `.env` in the runtime folder (`~/Library/Application Support/youtube-digest/`) with a random ntfy topic and a blank `ANTHROPIC_API_KEY` for you to fill in. Keys never go in the repo.

## Configure

Edit `config.toml` to change the channels, the run time, the model, or the audience description, then run `ytdigest install` again. A channel's ID starts with `UC` and appears as `"externalId"` in the page source of its YouTube page.

## Tests

Fourteen tests cover feed parsing and the fallback, first-run and later-run selection, seen-video tracking, prompt wrapping, response parsing, message splitting, notifications and config loading.
