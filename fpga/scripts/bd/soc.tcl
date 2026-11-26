# Block design for the Zybo Z7-10 QEC SoC (`system.bd`), sourced by build.tcl.
#
# Instantiates:
#   - Zynq-7000 PS7 with Zybo board DDR/MIO presets, PS UART1 enabled, and one
#     100 MHz fabric clock (`FCLK_CLK0`).
#   - Dual-channel 32-bit AXI GPIO mapped at 0x41200000: channel 1 (+0x00) is
#     ARM -> PL `ctrl` output, channel 2 (+0x08) is PL -> ARM `status` input.

# Add Zynq PS7, apply Zybo board presets, and enable UART1 + 100 MHz FCLK0.
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} \
    [get_bd_cells ps7]
set_property -dict [list \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100.000000} \
    CONFIG.PCW_UART1_PERIPHERAL_ENABLE {1} \
] [get_bd_cells ps7]

# Add dual-channel 32-bit AXI GPIO (ch1 out = ctrl, ch2 in = status) on M_AXI_GP0.
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 axi_gpio_0
set_property -dict [list \
    CONFIG.C_GPIO_WIDTH {32} \
    CONFIG.C_ALL_OUTPUTS {1} \
    CONFIG.C_IS_DUAL {1} \
    CONFIG.C_GPIO2_WIDTH {32} \
    CONFIG.C_ALL_INPUTS_2 {1} \
] [get_bd_cells axi_gpio_0]
apply_bd_automation -rule xilinx.com:bd_rule:axi4 \
    -config {Master "/ps7/M_AXI_GP0" Clk "Auto"} \
    [get_bd_intf_pins axi_gpio_0/S_AXI]
# Export GPIO channels, 100 MHz fabric clock, and active-low reset to top_qec_soc.sv.
make_bd_pins_external [get_bd_pins axi_gpio_0/gpio_io_o]
make_bd_pins_external [get_bd_pins axi_gpio_0/gpio2_io_i]
create_bd_port -dir O -type clk FCLK_CLK0_0
connect_bd_net [get_bd_ports FCLK_CLK0_0] [get_bd_pins ps7/FCLK_CLK0]
create_bd_port -dir O -type rst peripheral_aresetn_0
connect_bd_net [get_bd_ports peripheral_aresetn_0] \
    [get_bd_pins rst_ps7_100M/peripheral_aresetn]
# Pin AXI GPIO to 0x41200000 so it matches QEC_GPIO_BASE in platform.h.
assign_bd_address
set_property offset 0x41200000 [get_bd_addr_segs ps7/Data/SEG_axi_gpio_0_Reg]
