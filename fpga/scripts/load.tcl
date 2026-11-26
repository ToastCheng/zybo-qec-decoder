# Volatile JTAG loader for Zybo Z7-10 (run via XSCT; does not touch flash).
#
# Programs the PL bitstream, runs ps7_init/ps7_post_config to bring up DDR and
# fabric clocks, then downloads and starts the ARM Cortex-A9 firmware ELF.
# Usage: xsct fpga/scripts/load.tcl <bitstream> <elf> [xsa]

set bit [lindex $argv 0]
set elf [lindex $argv 1]
set xsa [lindex $argv 2]

if { $bit eq "" || $elf eq "" } {
    error "usage: xsct fpga/scripts/load.tcl <bitstream> <elf> [xsa]"
}

# Locate ps7_init.tcl in the sibling Vitis platform export, or unzip it from the XSA.
set app_dir  [file tail [file dirname [file dirname $elf]]]
set platform [string map {_app _platform} $app_dir]
set workspace [file dirname [file dirname [file dirname $elf]]]
set init_tcl [glob -nocomplain $workspace/$platform/export/$platform/hw/sdt/ps7_init.tcl]
if { $init_tcl eq "" && $xsa ne "" } {
    puts "ps7_init.tcl not found in platform export, extracting from $xsa ..."
    set init_dir [file join [file dirname $xsa] ps7_init]
    file mkdir $init_dir
    exec unzip -o -j $xsa ps7_init.tcl -d $init_dir
    set init_tcl [file join $init_dir ps7_init.tcl]
}
if { $init_tcl eq "" } {
    error "ps7_init.tcl not found (no platform export and no XSA given)"
}

connect

# Step 1: program the XC7Z010 programmable logic.
puts "Programming PL with $bit ..."
targets -set -nocase -filter {name =~ "*xc7z010*"}
fpga -file $bit

# Step 2: initialize PS clocks, MIO/UART1, DDR, and release PL level shifters.
puts "Initializing PS ..."
targets -set -nocase -filter {name =~ "APU*"}
source $init_tcl
ps7_init
ps7_post_config

# Step 3: reset Cortex-A9 core 0, load the firmware ELF into RAM, and run.
puts "Downloading $elf ..."
targets -set -nocase -filter {name =~ "ARM*#0"}
rst -processor
dow $elf
con

puts "Application running. Open the UART (115200 baud) to interact with it."
