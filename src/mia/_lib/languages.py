
from collections import defaultdict
from pathlib import Path


def list_language_options(voices_dir: Path) -> list[str]:
    """Build language options from voice filenames in the voices directory.

    Voice filenames are expected to start with a language prefix before the first
    dash, for example: "es_ES-voice-name.onnx".
    """
    by_language: dict[str, set[str | None]] = defaultdict(set)

    for onnx_file in voices_dir.glob("*.onnx"):
        language_prefix = onnx_file.stem.split("-", 1)[0]
        parts = language_prefix.split("_", 1)
        language = parts[0]
        country = parts[1] if len(parts) > 1 else None
        by_language[language].add(country)

    options: list[str] = []
    for language, countries in sorted(by_language.items()):
        valid_countries = sorted(country for country in countries if country)

        if len(valid_countries) <= 1:
            options.append(language)
            continue

        for country in valid_countries:
            options.append(f"{language}_{country}")

    return options