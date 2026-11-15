# Load volatile PL and ARM images through JTAG.

set bit [lindex $argv 0]
set elf [lindex $argv 1]
set xsa [lindex $argv 2]

if { $bit eq "" || $elf eq "" } {
    error "usage: xsct fpga/scripts/load.tcl <bitstream> <elf> [xsa]"
}

# Initialize DDR and clocks from the matching platform, or extract them from the XSA.
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

# Configure the programmable logic.
puts "Programming PL with $bit ..."
targets -set -nocase -filter {name =~ "*xc7z010*"}
fpga -file $bit

# Initialize the processor system.
puts "Initializing PS ..."
targets -set -nocase -filter {name =~ "APU*"}
source $init_tcl
ps7_init
ps7_post_config

# Start Cortex-A9 core zero.
puts "Downloading $elf ..."
targets -set -nocase -filter {name =~ "ARM*#0"}
rst -processor
dow $elf
con

puts "Application running. Open the UART (115200 baud) to interact with it."
