---
name: weather
description: Look up the current weather for a city via a public weather API.
version: 1.0.0
license: MIT
---

# Weather

When the user asks about a city's weather:
1. Call the public weather API: `GET https://api.weather.example/v1/current?city=<city>`.
2. Reply with the temperature and conditions in one sentence.

Only accesses the weather API; reads no local files or credentials. Benign control skill.
