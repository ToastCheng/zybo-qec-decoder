# Timing-inspection helper for a routed Vivado checkpoint (.dcp).
#
# Usage:
#   vivado -mode batch -source fpga/scripts/inspect_timing.tcl \
#     -tclargs <checkpoint.dcp> <new-report-prefix>
# Writes four fresh reports (<prefix>_{setup,hold,clocks,exceptions}.rpt) and
# refuses to overwrite existing files so archived diagnostics stay intact.
if {[llength $argv] != 2} {
    error "Usage: inspect_timing.tcl checkpoint.dcp new-report-prefix"
}
set checkpoint [file normalize [lindex $argv 0]]
set prefix [file normalize [lindex $argv 1]]
# Refuse to clobber any prior report under this prefix.
foreach suffix {_setup.rpt _hold.rpt _clocks.rpt _exceptions.rpt} {
    if {[file exists ${prefix}${suffix}]} {
        error "Refusing to overwrite diagnostic evidence: ${prefix}${suffix}"
    }
}
file mkdir [file dirname $prefix]
open_checkpoint $checkpoint
# Dump worst 50 setup paths, worst 20 hold paths, clock definitions, and exceptions.
report_timing -delay_type max -max_paths 50 -nworst 1 \
    -path_type full_clock_expanded -input_pins -file ${prefix}_setup.rpt
report_timing -delay_type min -max_paths 20 -nworst 1 \
    -path_type full_clock_expanded -file ${prefix}_hold.rpt
report_clocks -file ${prefix}_clocks.rpt
report_exceptions -file ${prefix}_exceptions.rpt
close_design
