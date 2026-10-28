"""Article -> Image pipeline: analyze the story, pick a visual idea, write a FLUX.1 schnell prompt, generate, quality-check, attach to WordPress.

Modules: config (settings), llm (provider-neutral text/vision calls), analyzer (story JSON), concept (safety rules), presets (style presets),
prompt_writer (schnell prompt), generator (image API + fit), checker (quality check), publisher (WordPress), meta (per-article log + history),
pipeline (orchestration), cli (python -m imagegen). Standard library plus Pillow only.
"""
