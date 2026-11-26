# Build Journal

A plain account of how the pipeline went from a design to a finished film, including what broke. Dates are 24-26 November 2026.

## 1. Foundation (24 Nov)

The first commits set up the contract: a JSON Schema for `storyboard.json` (8-12 shots, 60-90 s total), a validator, content-addressed caching, an append-only `runs.jsonl` audit log, and one CLI (`python -m pipeline.cli`) with a command per stage. Every stage has an offline `--mock` mode so the whole pipeline can be exercised without API keys or a GPU.

## 2. First real run (25 Nov)

Running the pipeline with real keys exposed a chain of problems that mock mode had hidden:

- **Black picture, silent audio.** The earlier mock runs had left 1x1-pixel images, 36-byte "videos" and silent WAV files in `outputs/`. The status command only counted that files existed, so it reported everything as generated. Lesson: validate content, not just presence.
- **Assembly used only the first shot.** The final FFmpeg command took `shot_01.mp4` as its only video input and never built the end card. It now normalises every clip to the target aspect ratio, joins all shots and the disclosure end card, then mixes audio.
- **Gemini TTS returned HTTP 400.** The request asked for an audio MIME type; Gemini TTS needs `responseModalities: ["AUDIO"]` plus a prebuilt voice, and returns base64 PCM. The default model name (`gemini-2.5-flash-tts`) did not exist; `gemini-2.5-flash-preview-tts` does.
- **Cloudflare showed `AUTH_FAILED` with a valid token.** The health check used the account-token verify endpoint; user-owned tokens verify at `/user/tokens/verify`. Separately, FLUX schnell now rejects `num_steps` (it wants `steps`) and `seed`.
- **Free-tier image generation is unavailable in Gemini** (quota 0), so a Gemini image fallback was written but is not usable on a free key. Cloudflare FLUX is the working image provider.

## 3. Making it watchable and listenable (25-26 Nov)

- **Motion.** The Wan 2.2 notebooks need a Kaggle GPU. As a local alternative, a Ken Burns stage animates each keyframe with a camera move (push-in, pan, tilt, zoom-out) chosen from the shot's `camera_movement`. This is camera motion over stills, not generated video.
- **Music.** The ACE-Step notebook was not run. A procedural generator now synthesises a clean solo fingerpicked guitar (Tizita-style D minor mode, 68 BPM) so the film has a full-length score. It sounds like a digital instrument, not a recording.
- **Narration sync.** Per-shot voice clips were being joined at their natural lengths, so speech drifted from the picture, and a stale combined track once held only the first line. Each clip is now placed on its own 7.5 s shot (slightly long clips are sped up, at most 1.25x), and the combined track is always rebuilt from every clip on disk.
- **Loudness.** The ten clips differed by about 5 dB. Each is now measured and gain-matched to the same level, within about 0.7 dB.
- **Captions.** English captions appear only while the line is spoken, timed from the actual clip lengths, with an outline for readability.
- **Mix.** Music sits at a low level and ducks under the voice; the narration is padded so the music continues through the end card.

## 4. Web studio (26 Nov)

A small standard-library web app turns a form (story idea, character, setting, length, voice, music, formats) into a storyboard with Gemini, validates it against the same schema, then runs the identical pipeline commands in an isolated folder. One run of an 8-shot film took about nine minutes, most of it the storyboard step. Google had retired `gemini-2.5-flash` for new keys, so the text model default became `gemini-flash-latest` with fallbacks.

## 5. Known limits

- Motion is Ken Burns camera movement; Wan 2.2 video generation is prepared (`kaggle/wan_batch.json`, notebook) but was not run.
- Music is synthesised, not ACE-Step.
- Narration is a separate Gemini TTS take per shot; tone can differ slightly between shots even though loudness is matched.
- FLUX schnell is prompted with repeated character traits, so the character is similar across shots but not identical.
- Amharic narration and translation were produced by AI and have not been reviewed by a native speaker. Treat them as a draft until they are.
