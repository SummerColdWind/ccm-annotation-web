# UI font

`ccm-ui-sans.woff2` is a variable-weight subset of Noto Sans SC, distributed under the SIL Open Font License 1.1 in `OFL.txt`.

`ccm-ui-serif.woff2` is a variable-weight subset of Noto Serif SC, distributed under the SIL Open Font License 1.1 in `OFL-serif.txt`. It supplies the workbench heading's actual 900 weight without relying on synthetic system-font bolding.

Official source: [Google Fonts / Noto Sans SC](https://github.com/google/fonts/tree/main/ofl/notosanssc).

Heading source: [Google Fonts / Noto Serif SC](https://github.com/google/fonts/tree/main/ofl/notoserifsc).

The subset covers the application and annotation rules. User-provided characters outside the subset use the operating system's CJK font fallback. Fonts are served locally; no Google Fonts or other CDN requests are made by the application.

To rebuild after adding new UI text, download the official `NotoSansSC[wght].ttf` into `output/font-source/NotoSansSC.ttf`, install `fonttools[woff]`, and run `python tools/build_ui_font.py`. This build step is optional for deployment; the generated WOFF2 file is included in the source package.

For the heading font, download `NotoSerifSC[wght].ttf` into `output/font-source/NotoSerifSC.ttf` and run `python tools/build_ui_font.py --family serif`.
