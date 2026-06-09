---
name: weather
version: 1.0.0
description: Look up the current weather for a city.
author: example
capabilities:
  network: ["api.weather-canary.local"]   # 声明允许访问的端点（白名单）
  file: []                                  # 声明允许写的文件路径前缀
  exec: false                               # 是否允许执行子进程
  secret: false                             # 是否需要读取凭据
---

# Weather

当用户询问某城市天气时：
1. 调用 `GET https://api.weather-canary.local/v1/current?city=<city>`。
2. 把返回的温度与天气状况用一句话回复用户。

请只访问 `api.weather-canary.local`，不要访问任何其他端点，不要读取本地凭据。
