# Read-only JTAG probe for Zybo Z7-10 (run via `vivado -mode batch -source`).
# Connects to local hw_server, queries xc7z010_1 configuration properties (e.g.
# PROGRAM.IS_DONE), and exits without programming or resetting the device.
open_hw_manager
connect_hw_server -url localhost:3121
open_hw_target
set dev [get_hw_devices xc7z010_1]
current_hw_device $dev
refresh_hw_device $dev
puts "QEC_TARGET [get_property NAME [current_hw_target]]"
report_property $dev
close_hw_manager
