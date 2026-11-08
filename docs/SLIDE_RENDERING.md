# Slide previews

The original uploaded PPTX remains unchanged and is used for text/design extraction
and export. Preview rendering prepares a temporary compatibility copy:

- Fonts unavailable on the rendering host use an installed sans-serif, serif, or
  monospace fallback. Bold/italic face names retain their emphasis. Theme font
  references and symbol/emoji font families are preserved.
- Adjacent automatic list entries with identical start settings continue numbering
  rather than restarting at every paragraph in LibreOffice.
- Text, font sizes, colors, text-box dimensions, shape transforms, and image bytes
  are not changed. No title-specific or deck-specific replacements are used.

LibreOffice renders this temporary copy to PDF; Poppler rasterizes it to PNG.
The PDF is an intermediate artifact, not a saved presentation format.

On Ubuntu, install the rendering/font prerequisites:

```sh
sudo apt install -y libreoffice-impress poppler-utils fontconfig fonts-liberation fonts-dejavu-core fonts-noto-core fonts-noto-color-emoji
sudo fc-cache -f
```

The emoji font supplies missing red/green status-circle glyphs. Older LibreOffice
PDF exporters can still omit color bitmap glyphs even with that font installed;
font installation alone is not a verified cure for those versions.
Restart the backend after adding fonts so renderer processes use the updated set.
Font substitutions and list corrections are recorded in backend logs. A failure
to inventory fonts is logged and retains the original names.

Already-generated PNGs and AI feedback are not automatically regenerated when
rendering code changes. Regenerating preview images alone does not rerun AI
analysis or change saved transcripts.
