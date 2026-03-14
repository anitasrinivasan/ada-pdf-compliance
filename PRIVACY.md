# Privacy Policy

**ADA PDF Compliance Plugin**
Last updated: March 13, 2026

## Overview

This is an open-source Claude Code plugin that runs entirely on your local machine. It is designed with privacy in mind.

## Data Collection

This plugin does **not** collect, transmit, store, or share any personal data or document content. Specifically:

- **No telemetry** -- No usage data, analytics, or crash reports are sent anywhere.
- **No network requests** -- All PDF analysis and fixes happen locally using Python libraries (pypdf, pikepdf). No files or metadata are uploaded to any server.
- **No accounts** -- No sign-up, login, or API keys are required for this plugin.

## How It Works

1. The plugin reads your PDF files from your local filesystem.
2. It analyzes accessibility metadata using local Python scripts.
3. It writes fixed PDFs back to your local filesystem (as `_accessible.pdf`).
4. All processing happens on your machine.

## Third-Party Services

This plugin runs within Claude Code, which is subject to [Anthropic's Privacy Policy](https://www.anthropic.com/privacy). The plugin itself does not introduce any additional data collection beyond what Claude Code provides.

## Contact

For questions about this privacy policy, open an issue at:
https://github.com/anitasrinivasan/ada-pdf-compliance/issues

## License

This privacy policy is provided under the same MIT license as the plugin.
