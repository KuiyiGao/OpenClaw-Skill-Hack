SB := sandbox
LC := ./$(SB)/labctl.sh
MSG ?= Introduce yourself in one sentence.

.PHONY: help oc-build oc-up oc-down oc-ask oc-watch oc-ui oc-exfil oc-events oc-verify oc-skills oc-shell

help:
	@$(LC) help
	@echo ""
	@echo "make oc-build   build images (Node 24 + npm i -g openclaw)"
	@echo "make oc-up / oc-down            start / stop the lab"
	@echo "make oc-ask MSG=\"...\"           inner agent answer + step trace"
	@echo "make oc-watch / oc-ui           outer monitor: stream / web dashboard"
	@echo "make oc-exfil                   captured exfil payloads"
	@echo "make oc-verify                  egress-lock self-test"

oc-build:
	docker build -f $(SB)/Dockerfile          -t asshack-sandbox:latest  .
	docker build -f $(SB)/Dockerfile.openclaw -t asshack-openclaw:latest .

oc-up:
	@$(LC) up

oc-down:
	@$(LC) down

oc-ask:
	@$(LC) ask "$(MSG)"

oc-watch:
	@$(LC) watch

oc-ui:
	@$(LC) ui

oc-exfil:
	@$(LC) exfil

oc-events:
	@$(LC) events

oc-verify:
	@$(LC) verify

oc-skills:
	@$(LC) skill list

oc-shell:
	docker compose -f $(SB)/docker-compose.yml --env-file $(SB)/.env exec openclaw bash
