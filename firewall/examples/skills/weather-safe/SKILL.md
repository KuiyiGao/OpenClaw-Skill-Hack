---
name: weather-safe
description: Look up the current weather for a city by name. Network-free; reads only ./weather/<city>.json from the workspace.
version: 0.1.0
license: MIT
allow_hosts: []
allowed_tools: ["Read"]
---

# weather-safe

A minimal example skill that does exactly what its description says.
It reads `./weather/<city>.json` (already on disk in the workspace),
parses the JSON, and returns the temperature.

**This skill makes no network calls.** That is the whole contract; the
firewall's runtime layer will see no egress events for this skill.

## Usage

When asked for weather, read the file and return a one-line summary.
