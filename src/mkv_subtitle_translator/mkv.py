from __future__ import annotations

import contextlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from mkv_subtitle_translator.analyzer import SubtitleAnalyzer

# ============================================================================
# MKV Container Management (unchanged from original)
# ============================================================================


def get_mkv_subtitle_streams(mkv_file: str) -> list[dict]:
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "s",
            "-show_entries",
            "stream=index,codec_name,tags:stream_tags=language,title",
            "-of",
            "json",
            mkv_file,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return data.get("streams", [])
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def extract_subtitle_from_mkv(mkv_file: str, stream_index: int, output_file: str) -> bool:
    try:
        cmd = [
            "ffmpeg",
            "-i",
            mkv_file,
            "-map",
            f"0:s:{stream_index}",
            "-c:s",
            "srt",
            output_file,
            "-y",
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def extract_best_subtitle_from_mkv(mkv_file: str) -> str | None:
    """Extract the most appropriate subtitle from MKV"""
    print(f"\nExtracting subtitles from {Path(mkv_file).name}")

    streams = get_mkv_subtitle_streams(mkv_file)
    if not streams:
        print("  No subtitle streams found")
        return None

    print(f"  Found {len(streams)} subtitle stream(s)")

    temp_dir = tempfile.mkdtemp()
    extracted_files = []
    analyzer = SubtitleAnalyzer()

    for i, stream in enumerate(streams):
        temp_file = os.path.join(temp_dir, f"subtitle_{i}.srt")

        if extract_subtitle_from_mkv(mkv_file, i, temp_file):
            file_size = os.path.getsize(temp_file)
            if file_size > 0:
                lang = stream.get("tags", {}).get("language", "unknown")
                is_sdh = analyzer.is_sdh_subtitle(temp_file)

                print(
                    f"    Stream {i}: {lang} - {file_size:,} bytes" + (" (SDH)" if is_sdh else "")
                )

                extracted_files.append(
                    {
                        "path": temp_file,
                        "size": file_size,
                        "language": lang.lower(),
                        "is_sdh": is_sdh,
                        "index": i,
                    }
                )

    if not extracted_files:
        print("  Failed to extract any subtitles")
        return None

    # Select best subtitle
    english_subs = [f for f in extracted_files if f["language"] in ["eng", "en", "english"]]

    if english_subs:
        non_sdh = [f for f in english_subs if not f["is_sdh"]]
        selected_file = max(non_sdh or english_subs, key=lambda x: x["size"])
    else:
        non_sdh = [f for f in extracted_files if not f["is_sdh"]]
        selected_file = max(non_sdh or extracted_files, key=lambda x: x["size"])

    output_path = f"{os.path.splitext(mkv_file)[0]}.extracted.srt"
    with open(selected_file["path"], encoding="utf-8") as src:
        content = src.read()
    with open(output_path, "w", encoding="utf-8") as dst:
        dst.write(content)

    # Cleanup
    for f in extracted_files:
        with contextlib.suppress(OSError):
            os.remove(f["path"])
    with contextlib.suppress(OSError):
        os.rmdir(temp_dir)

    print(f"  ✓ Extracted to: {output_path}")
    return output_path


def merge_subtitles_into_mkv(mkv_file: str, subtitle_files: list[str], backup: bool = True) -> bool:
    """Merge subtitle files into MKV container"""
    print(f"\nMerging subtitles into {Path(mkv_file).name}")

    temp_output = f"{mkv_file}.temp.mkv"

    try:
        existing_streams = get_mkv_subtitle_streams(mkv_file)
        estonian_streams = [
            i
            for i, stream in enumerate(existing_streams)
            if stream.get("tags", {}).get("language", "").lower() in ["est", "et", "estonian"]
        ]

        if estonian_streams:
            count = len(estonian_streams)
            print(f"  Found {count} existing Estonian subtitle stream(s) - will replace")

        cmd = ["ffmpeg", "-i", mkv_file]

        for sub_file in subtitle_files:
            cmd.extend(["-i", sub_file])

        cmd.extend(["-map", "0:v?", "-map", "0:a?"])

        for i, stream in enumerate(existing_streams):
            lang = stream.get("tags", {}).get("language", "").lower()
            if lang not in ["est", "et", "estonian"]:
                cmd.extend(["-map", f"0:s:{i}"])

        for i in range(len(subtitle_files)):
            cmd.extend(["-map", f"{i + 1}:0"])

        cmd.extend(["-c", "copy"])

        non_estonian_count = len(
            [
                s
                for s in existing_streams
                if s.get("tags", {}).get("language", "").lower() not in ["est", "et", "estonian"]
            ]
        )

        for i in range(len(subtitle_files)):
            sub_idx = non_estonian_count + i
            cmd.extend([f"-metadata:s:s:{sub_idx}", "language=est"])
            cmd.extend([f"-metadata:s:s:{sub_idx}", "title=Estonian (Translated)"])

        cmd.extend(["-y", temp_output])

        print("  Running ffmpeg...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"  Error: {result.stderr}")
            return False

        if backup:
            backup_file = f"{mkv_file}.backup"
            if os.path.exists(backup_file):
                os.remove(backup_file)
            print(f"  Creating backup: {backup_file}")
            os.rename(mkv_file, backup_file)

        os.rename(temp_output, mkv_file)
        print("  ✅ Successfully merged subtitles")

        return True

    except Exception as e:
        print(f"  Error: {e}")
        if os.path.exists(temp_output):
            os.remove(temp_output)
        return False
