"""Turn the web form's inputs into a schema-valid storyboard.json.

Gemini writes the creative parts (title, character, per-shot scene / narration / prompts).
Everything structural (ids, durations, music, end card, aspect ratios, seeds) is assembled in code and
validated with the pipeline's own validator, so the pipeline stages receive exactly what they expect.
"""

import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import requests

from pipeline.config import get_config
from pipeline.validator import validate_storyboard_dict

SHOT_SECONDS = 7.5
MIN_SHOTS, MAX_SHOTS = 8, 12

# Phrases the Ken Burns stage understands (see pipeline.utils.ffmpeg.pick_motion)
CAMERA_MOVES = [
    "Slow forward dolly",
    "Subtle push-in",
    "Slow pan right",
    "Slow pan left",
    "Slow tilt up",
    "Slow tilt down",
    "Slow zoom out to reveal",
    "Static macro",
]

MUSIC_PROMPTS = {
    "guitar": (
        "Clean solo fingerpicked acoustic nylon-string guitar, slow and warm, gentle arpeggios, "
        "no other instruments, intimate and reflective.",
        ["Acoustic guitar"],
    ),
    "ensemble": (
        "Traditional acoustic instrumental music with a sustained bowed drone, soft wooden flute, "
        "plucked strings and a slow hand drum, meditative and warm.",
        ["Bowed strings", "Flute", "Plucked strings", "Hand drum"],
    ),
}

DEFAULT_STYLE = {
    "art_style": "Cinematic documentary, warm photorealistic 35mm film aesthetic, rich textural detail",
    "lighting": "Soft natural directional light, warm golden tones",
    "color_palette": "Earthy ochre, terracotta, deep brown and warm gold accents",
}
CAMERA_LENS = "Arri Alexa LF look, 50mm f/1.4 prime lens, shallow depth of field, creamy bokeh"
FILM_GRAIN = "Subtle organic Kodak Vision3 250D grain"
NEGATIVE = (
    "text, watermark, logo, cartoon, low resolution, blurred details, deformed hands, "
    "distorted anatomy, extra fingers, plastic skin"
)


class StoryboardError(Exception):
    pass


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:24] or "hero"


def _ascii(text: str, fallback: str) -> str:
    out = re.sub(r"[^A-Za-z0-9 .,&-]", "", text or "").strip()
    return out[:60] or fallback


def build_prompt(inputs: Dict[str, Any], previous_errors: Optional[List[str]] = None) -> str:
    n = int(inputs["shots"])
    example = {
        "film_title": "Title in English",
        "title_english": "Short English title, ASCII letters only",
        "story_description": "Two sentences describing the film.",
        "mood": "three or four mood words",
        "character": {
            "name": "A fictional character name",
            "description": "One or two sentences describing the fictional character",
            "estimated_age": "72 years old",
            "attire": "clothing description",
            "facial_features": "face and skin description",
            "hair": "hair description",
        },
        "visual_style": {"art_style": "...", "lighting": "...", "color_palette": "..."},
        "shots": [
            {
                "scene_description": "What we see, one or two sentences.",
                "narration_amharic": "ONE poetic sentence of Amharic in Ge'ez (Fidel) script, 10-16 words.",
                "english_translation": "Faithful English translation of that sentence.",
                "image_prompt": "Self-contained photographic image prompt for a text-to-image model.",
                "motion_prompt": "How the camera and subject move during the shot.",
                "camera_movement": "one value from the allowed list",
                "has_character": True,
                "visual_purpose": "Why this shot is in the story.",
            }
        ],
    }
    lines = [
        "You are a film director and Amharic poet creating a short film storyboard.",
        f"Return ONLY a JSON object, no markdown, with exactly {n} items in `shots`.",
        "",
        "USER INPUTS",
        f"- Story idea: {inputs['idea']}",
        f"- Title (may be empty, then invent one): {inputs.get('title') or ''}",
        f"- Main character (may be empty, then invent a FICTIONAL one): {inputs.get('character') or ''}",
        f"- Setting / culture: {inputs.get('setting') or 'unspecified'}",
        "",
        "RULES",
        f"- The {n} shots tell one clear story with a beginning, middle and end; each shot advances it.",
        "- narration_amharic: exactly ONE sentence in authentic Amharic Ge'ez script that can be spoken in "
        "about 6-7 seconds (10-16 words). english_translation must faithfully match it.",
        "- Each image_prompt must be fully self-contained (describe the place, light, subject, composition) and "
        "photographic. When has_character is true, repeat the character's key visual traits so they look the same "
        "in every shot. Never put text, captions or logos in images. Characters are fictional, never real people.",
        f"- camera_movement must be one of: {', '.join(CAMERA_MOVES)}. Vary it across shots.",
        "- Show the story through what the viewer SEES; narration adds meaning, it does not describe the picture.",
        "",
        "JSON SHAPE (shots array must contain " + str(n) + " items):",
        json.dumps(example, ensure_ascii=False, indent=1),
    ]
    if previous_errors:
        lines += ["", "YOUR PREVIOUS ANSWER WAS REJECTED. Fix these problems:", *[f"- {e}" for e in previous_errors]]
    return "\n".join(lines)


def _parse_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


FALLBACK_TEXT_MODELS = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash"]


def call_gemini(prompt: str) -> str:
    """Call Gemini for JSON text; falls back to other models if one is retired (404) or overloaded (503)."""
    cfg = get_config().gemini
    if not cfg.is_configured:
        raise StoryboardError("GEMINI_API_KEY is not configured in .env.")
    models = [cfg.text_model] + [m for m in FALLBACK_TEXT_MODELS if m != cfg.text_model]
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9},
    }
    last = ""
    for model in models:
        url = f"{cfg.api_endpoint}/models/{model}:generateContent?key={cfg.api_key}"
        for attempt in range(3):
            resp = requests.post(url, json=body, timeout=180)
            if resp.status_code == 200:
                try:
                    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError):
                    last = f"{model}: no text in response"
                    break
            last = f"{model} HTTP {resp.status_code}: {resp.text[:160]}"
            if resp.status_code in (429, 500, 503):
                time.sleep(8 * (attempt + 1))
                continue
            break  # 404 / 400 etc: try the next model
    raise StoryboardError(f"Gemini storyboard request failed ({last})")


def assemble_storyboard(inputs: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Combine user inputs with the LLM's creative payload into a full storyboard dict."""
    n = int(inputs["shots"])
    raw_shots = payload.get("shots") or []
    if len(raw_shots) != n:
        raise StoryboardError(f"Expected {n} shots but got {len(raw_shots)}")

    title = (payload.get("film_title") or inputs.get("title") or "Untitled Short Film").strip()
    english_title = _ascii(payload.get("title_english") or inputs.get("title") or "", "AI Short Film")
    total = round(n * SHOT_SECONDS, 1)

    ch = payload.get("character") or {}
    char_name = (ch.get("name") or "Main character").strip()
    char_id = "char_" + _slug(char_name)
    traits = {
        "estimated_age": ch.get("estimated_age") or "adult",
        "attire": ch.get("attire") or "traditional attire",
        "facial_features": ch.get("facial_features") or "warm, expressive features",
        "hair": ch.get("hair") or "natural hair",
    }
    char_desc = (ch.get("description") or f"{char_name}, a fictional character.").strip()
    if "fictional" not in char_desc.lower():
        char_desc += " Completely fictional AI-generated character."
    character = {
        "character_id": char_id,
        "name": char_name,
        "description": char_desc,
        "visual_traits": traits,
        "reference_image_path": None,
    }

    vs = {**DEFAULT_STYLE, **{k: v for k, v in (payload.get("visual_style") or {}).items() if v}}
    visual_style = {
        "art_style": vs["art_style"],
        "lighting": vs["lighting"],
        "color_palette": vs["color_palette"],
        "camera_lens": CAMERA_LENS,
        "film_grain": FILM_GRAIN,
        "negative_prompt": NEGATIVE,
    }
    style_suffix = f"{vs['art_style']}, {vs['lighting']}, photorealistic, highly detailed"

    shots = []
    for i, s in enumerate(raw_shots):
        has_char = bool(s.get("has_character"))
        prompt = (s.get("image_prompt") or s.get("scene_description") or "").strip()
        if has_char:
            prompt += f" Subject: {char_name}, {traits['estimated_age']}, {traits['facial_features']}, {traits['attire']}."
        prompt = f"{prompt} {style_suffix}"[:1900]
        move = s.get("camera_movement") or CAMERA_MOVES[i % len(CAMERA_MOVES)]
        shots.append(
            {
                "shot_id": f"shot_{i + 1:02d}",
                "duration": SHOT_SECONDS,
                "scene_description": (s.get("scene_description") or "Scene").strip(),
                "narration_amharic": (s.get("narration_amharic") or "").strip(),
                "english_translation": (s.get("english_translation") or "").strip(),
                "image_prompt": prompt,
                "motion_prompt": (s.get("motion_prompt") or move).strip(),
                "camera_movement": move,
                "character_reference_ids": [char_id] if has_char else [],
                "visual_purpose": (s.get("visual_purpose") or "Advance the story.").strip(),
                "generation_settings": {"seed": 42000 + i + 1, "steps": 30, "guidance_scale": 7.5, "fps": 24},
            }
        )

    music_prompt, instruments = MUSIC_PROMPTS.get(inputs.get("music", "guitar"), MUSIC_PROMPTS["guitar"])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "project_metadata": {
            "project_name": english_title,
            "pipeline_version": "1.0.0",
            "target_total_duration": total,
            "created_at": now,
            "updated_at": now,
            "description": (payload.get("story_description") or inputs["idea"])[:300],
        },
        "film_title": title,
        "story_description": (payload.get("story_description") or inputs["idea"]).strip(),
        "target_audience": "General audience",
        "narration_language": "Amharic",
        "subtitle_language": "English",
        "output_aspect_ratios": inputs.get("aspects") or ["16:9", "9:16"],
        "character_references": [character],
        "visual_style": visual_style,
        "music_settings": {
            "prompt": music_prompt,
            "genre": "Acoustic",
            "instrumentation": instruments,
            "tempo_bpm": 68,
            "mood": (payload.get("mood") or "Warm, reflective").strip(),
            "target_duration": total + 3.0,
            "ducking_attenuation_db": -14.0,
        },
        "end_card_settings": {
            "title": english_title,
            "disclosure_text": "This film was created with AI tools. Characters and events are fictional.",
            "duration_seconds": 4.0,
            "background_color": "#120e0b",
            "font_color": "#e8d8c8",
        },
        "shots": shots,
    }


def generate_storyboard(
    inputs: Dict[str, Any],
    llm: Callable[[str], str] = call_gemini,
    attempts: int = 3,
) -> Dict[str, Any]:
    """Ask the LLM for the creative content, assemble and validate; retry with the validator's feedback."""
    errors: Optional[List[str]] = None
    last_exc = ""
    for _ in range(attempts):
        try:
            payload = _parse_json(llm(build_prompt(inputs, errors)))
            storyboard = assemble_storyboard(inputs, payload)
            ok, errs = validate_storyboard_dict(storyboard)
            if ok:
                return storyboard
            errors = errs
            last_exc = "; ".join(errs)
        except StoryboardError as exc:
            if "GEMINI_API_KEY" in str(exc):
                raise
            errors = [str(exc)]
            last_exc = str(exc)
        except (json.JSONDecodeError, ValueError) as exc:
            errors = [f"Output was not valid JSON ({exc})"]
            last_exc = errors[0]
    raise StoryboardError(f"Could not produce a valid storyboard: {last_exc}")
