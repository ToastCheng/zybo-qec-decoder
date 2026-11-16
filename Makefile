.DEFAULT_GOAL := help
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON ?= $(ROOT)/qec/.venv/bin/python
VIVADO ?= vivado
VITIS ?= vitis
XSCT ?= xsct
IMAGE_DIR ?= $(ROOT)/build/image
PORT ?= 8765
SERIAL_PORT ?=

export PYTHONPYCACHEPREFIX := $(ROOT)/build/cache/python
export RUFF_CACHE_DIR := $(ROOT)/build/cache/ruff

.PHONY: help test sim build firmware load status web lint clean-cache

help:
	@printf '%s\n' 'make test / sim / build / firmware / load / status / web / lint' \
	  'make web SERIAL_PORT=/dev/ttyUSB1 PORT=8765' \
	  'IMAGE_DIR selects a fresh FPGA build directory (default: build/image).'

test:
	cd "$(ROOT)" && $(PYTHON) -m pytest qec/tests scripts/test_source_docs.py -q
	cd "$(ROOT)" && node --test qec/tests/*.cjs

sim:
	cd "$(ROOT)" && $(PYTHON) scripts/simulate.py --bench core --build-dir "$(ROOT)/build/sim/core"
	cd "$(ROOT)" && $(PYTHON) scripts/simulate.py --bench bridge --build-dir "$(ROOT)/build/sim/bridge"
	cd "$(ROOT)" && $(PYTHON) scripts/simulate.py --bench counter --build-dir "$(ROOT)/build/sim/counter"

build:
	mkdir -p "$(ROOT)/build/tools" "$(ROOT)/build/logs"
	cd "$(ROOT)/build/tools" && $(VIVADO) -mode batch -log "$(ROOT)/build/logs/vivado.log" -journal "$(ROOT)/build/logs/vivado.jou" -source "$(ROOT)/fpga/scripts/build.tcl" -tclargs "$(abspath $(IMAGE_DIR))"

firmware:
	mkdir -p "$(ROOT)/build/tools" "$(ROOT)/build/logs"
	cd "$(ROOT)/build/tools" && QEC_IMAGE_DIR="$(abspath $(IMAGE_DIR))" $(VITIS) -s "$(ROOT)/fpga/vitis/build.py" > "$(ROOT)/build/logs/vitis.log" 2>&1

load:
	mkdir -p "$(ROOT)/build/tools" "$(ROOT)/build/logs"
	cd "$(ROOT)/build/tools" && $(XSCT) "$(ROOT)/fpga/scripts/load.tcl" "$(abspath $(IMAGE_DIR))/qec_soc.bit" "$(abspath $(IMAGE_DIR))/vitis_ws/qec_app/build/qec_app.elf" "$(abspath $(IMAGE_DIR))/qec_soc.xsa" > "$(ROOT)/build/logs/program.log" 2>&1

status:
	mkdir -p "$(ROOT)/build/tools" "$(ROOT)/build/logs"
	cd "$(ROOT)/build/tools" && $(VIVADO) -mode batch -log "$(ROOT)/build/logs/status.log" -journal "$(ROOT)/build/logs/status.jou" -source "$(ROOT)/fpga/scripts/status.tcl"

web:
	cd "$(ROOT)" && $(PYTHON) -m qec.surface.web --port $(PORT) $(if $(SERIAL_PORT),--serial-port "$(SERIAL_PORT)",)

lint:
	cd "$(ROOT)" && uvx ruff check qec/surface qec/tests fpga/vitis scripts

clean-cache:
	rm -rf "$(ROOT)/build/cache" "$(ROOT)/build/sim" "$(ROOT)/build/tools"
