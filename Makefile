# OpenClaw isolation lab (real LLM). First: cp sandbox/.env.example sandbox/.env and set your key.
SB := sandbox
CF := docker compose -f $(SB)/docker-compose.yml --env-file $(SB)/.env
MSG ?= Introduce yourself in one sentence.

.PHONY: help oc-build oc-up oc-down oc-ask oc-monitor oc-skills oc-shell

help:
	@echo "make oc-build           build the OpenClaw image (Node 24 + npm i -g openclaw)"
	@echo "make oc-up              start the locked sandbox (egress-proxy + canary + openclaw)"
	@echo "make oc-ask MSG=\"...\"    ask OpenClaw (real model)"
	@echo "make oc-monitor         stream OpenClaw output / canary hits / blocked egress"
	@echo "make oc-skills          list installed skills"
	@echo "make oc-down            stop and clean up"
	@echo "skill gate:  ./sandbox/skillctl.sh add <skill_dir>   (Cisco scan gate + your approval)"

oc-build:
	docker build -f $(SB)/Dockerfile          -t asshack-sandbox:latest  .
	docker build -f $(SB)/Dockerfile.openclaw -t asshack-openclaw:latest .

oc-up:
	@test -f $(SB)/.env || { echo "first: cp $(SB)/.env.example $(SB)/.env and set LLM_API_KEY"; exit 1; }
	$(CF) up -d
	@echo "up. try: make oc-ask MSG=\"hi\"  /  make oc-monitor"

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
