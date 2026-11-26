# Zybo Z7-10 physical pin constraints for top_qec_soc.sv.
#
# Clocking: the Zynq PS7 IP automatically supplies the 100 MHz FCLK_CLK0 timing
# constraint; DDR and MIO/UART1 pins are fixed inside the PS7 hard block.
#
# User LEDs (LVCMOS33) mirror mailbox status bits from ps_bridge:
#   led[0] (M14) = status[0]  (READ_DATA bit 0 of last metadata read)
#   led[1] (M15) = status[29] (command ERROR)
#   led[2] (G14) = status[30] (decode DONE, high even on errored decode)
#   led[3] (D18) = status[31] (ACK toggle phase)
set_property -dict { PACKAGE_PIN M14 IOSTANDARD LVCMOS33 } [get_ports {led[0]}]
set_property -dict { PACKAGE_PIN M15 IOSTANDARD LVCMOS33 } [get_ports {led[1]}]
set_property -dict { PACKAGE_PIN G14 IOSTANDARD LVCMOS33 } [get_ports {led[2]}]
set_property -dict { PACKAGE_PIN D18 IOSTANDARD LVCMOS33 } [get_ports {led[3]}]
