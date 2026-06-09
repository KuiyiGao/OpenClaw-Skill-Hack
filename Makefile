# 便捷入口。两块：① OpenClaw 隔离实验室（真实 LLM，当前重点）② 攻防研究框架（离线）。
SB := sandbox
CF := docker compose -f $(SB)/docker-compose.yml --env-file $(SB)/.env
MSG ?= 用一句话介绍你自己

.PHONY: help oc-build oc-up oc-down oc-ask oc-monitor oc-skills oc-shell demo test

help:
	@echo "OpenClaw 隔离实验室（真实 LLM；先 cp $(SB)/.env.example $(SB)/.env 并填 key）:"
	@echo "  make oc-build              构建 OpenClaw 镜像（Node24 + npm i -g openclaw）"
	@echo "  make oc-up                 启动锁定沙箱（egress 允许列表 + canary + openclaw 常驻）"
	@echo "  make oc-ask MSG=\"...\"       让 OpenClaw 回答（真实模型），看它的反应"
	@echo "  make oc-monitor            监控入口：OpenClaw 反应 / canary 命中 / 被拦截的外泄"
	@echo "  make oc-skills             列出 OpenClaw 已装技能"
	@echo "  make oc-down               停止并清理"
	@echo "  技能门控：  ./sandbox/skillctl.sh add <skill_dir>   （Cisco 扫描门 + 你批准）"
	@echo ""
	@echo "攻防研究框架（离线，零依赖）:"
	@echo "  make demo                  攻击→(防御)→指标 demo"
	@echo "  make test                  单测"

oc-build:
	docker build -f $(SB)/Dockerfile          -t asshack-sandbox:latest  .
	docker build -f $(SB)/Dockerfile.openclaw -t asshack-openclaw:latest .

oc-up:
	@test -f $(SB)/.env || { echo "请先: cp $(SB)/.env.example $(SB)/.env 并填入 LLM_API_KEY"; exit 1; }
	$(CF) up -d
	@echo "已启动。试试: make oc-ask MSG=\"你好\"  /  make oc-monitor"

oc-down:
	$(CF) down

oc-ask:
	-$(CF) exec -T openclaw bash -lc 'openclaw agent --local --model real/$$LLM_MODEL \
	  --session-key agent:lab:1 --message "$(MSG)" --json'

oc-monitor:
	./sandbox/monitor.sh

oc-skills:
	./sandbox/skillctl.sh list

oc-shell:
	$(CF) exec openclaw bash

demo:
	python3 scripts/run_demo.py

test:
	python3 -m pytest tests/ -q
