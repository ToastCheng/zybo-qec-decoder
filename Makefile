# Standalone Zybo Z7-10 QEC decoders. Run from the repository root.
.DEFAULT_GOAL := help
PYTHON ?= python
VIVADO ?= vivado
VITIS ?= vitis
XSCT ?= xsct
XVLOG ?= xvlog
XELAB ?= xelab
XSIM ?= xsim
SOC_TOP ?= top_surface_soc
APP ?= surface
SOC_NAME = $(SOC_TOP:top_%=%)
TB ?= tb_qec_decoder

.PHONY: help test example sim sim_surface sim_bridge build_soc app run_soc readback reports netlist clean
help:
	@printf '%s\n' 'make test / example / sim / sim_surface / sim_bridge' \
	  'make build_soc / app / run_soc / readback (surface defaults)' \
	  'Repetition: make build_soc SOC_TOP=top_qec_soc; make app APP=qec' \
	  '           make run_soc SOC_TOP=top_qec_soc APP=qec' \
	  'make reports MODE=core|uart; make netlist (after MODE=core)' \
	  'Activate qec/.venv first; see README for setup and transport details.'
test:
	$(PYTHON) -m pytest qec/tests -q
example:
	$(PYTHON) -m qec.surface.example
sim:
	$(PYTHON) scripts/qec_sim.py
sim_surface:
	@mkdir -p build
	$(PYTHON) qec/surface/sim.py --distance 3 --basis z --shots 256 > build/surface_sim_d3.log 2>&1
	$(PYTHON) qec/surface/sim.py --distance 5 --basis z --shots 128 > build/surface_sim_d5.log 2>&1
	$(PYTHON) qec/surface/sim.py --distance 3 --basis x --shots 128 > build/surface_sim_x.log 2>&1
sim_bridge:
	@mkdir -p build
	$(XVLOG) --sv rtl/common/qec_decoder.sv rtl/common/qec_ps_bridge.sv qec/tb_ps_bridge.sv
	$(XELAB) tb_ps_bridge -s qec_ps_bridge
	$(XSIM) qec_ps_bridge -runall > build/qec_ps_bridge.log 2>&1
	$(XVLOG) --sv rtl/common/surface_decoder.sv rtl/common/surface_ps_bridge.sv qec/surface/tb_bridge.sv
	$(XELAB) tb_surface_bridge -s surface_bridge
	$(XSIM) surface_bridge -runall > build/surface_bridge_sim.log 2>&1
	$(PYTHON) scripts/check_sim_logs.py build/qec_ps_bridge.log build/surface_bridge_sim.log
build_soc:
	@mkdir -p build
	$(VIVADO) -mode batch -source scripts/build_soc.tcl -tclargs $(SOC_TOP)
app:
	$(VITIS) -s vitis/$(APP)/build_app.py
run_soc:
	$(XSCT) scripts/run_soc.tcl build/$(SOC_NAME).bit build/vitis_ws/$(APP)_app/build/$(APP)_app.elf build/$(SOC_NAME).xsa
readback:
	$(VIVADO) -mode batch -source scripts/qec_readback.tcl
MODE ?= core
reports:
	$(VIVADO) -mode batch -source scripts/qec_build.tcl -tclargs $(MODE)
netlist:
	$(PYTHON) scripts/qec_sim.py --netlist
clean:
	rm -rf build/ xsim.dir/ .Xil/
	rm -f *.pb *.log *.jou *.str
