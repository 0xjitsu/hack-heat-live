.PHONY: lint test secrets freshness build deploy-check run

lint:
	python3 -m hackheat.ci lint

test:
	python3 -m unittest discover -s tests -v

secrets:
	python3 -m hackheat.ci secrets

freshness:
	python3 -m hackheat.ci freshness

build:
	python3 -m hackheat.ci package

deploy-check:
	python3 -m hackheat.ci deploy-check

run:
	python3 -m hackheat.http_api
