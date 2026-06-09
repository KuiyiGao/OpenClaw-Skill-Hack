---
name: json-formatter
version: 1.0.0
description: Pretty-print and validate JSON the user provides.
author: example
capabilities:
  network: []
  file: []
  exec: false
  secret: false
---

# JSON Formatter

当用户给出一段 JSON 文本时：
1. 解析并校验其合法性。
2. 以 2 空格缩进美化输出。
3. 若非法，指出第一个错误的位置与原因。

不访问网络，不读取任何文件或凭据，纯文本处理。
