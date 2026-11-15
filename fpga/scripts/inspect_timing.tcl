# Read a checkpoint and write new setup, hold, clock and exception reports.
if {[llength $argv] != 2} {
    error "Usage: inspect_timing.tcl checkpoint.dcp new-report-prefix"
}
set checkpoint [file normalize [lindex $argv 0]]
set prefix [file normalize [lindex $argv 1]]
foreach suffix {_setup.rpt _hold.rpt _clocks.rpt _exceptions.rpt} {
    if {[file exists ${prefix}${suffix}]} {
        error "Refusing to overwrite diagnostic evidence: ${prefix}${suffix}"
    }
}
file mkdir [file dirname $prefix]
open_checkpoint $checkpoint
report_timing -delay_type max -max_paths 50 -nworst 1 \
    -path_type full_clock_expanded -input_pins -file ${prefix}_setup.rpt
report_timing -delay_type min -max_paths 20 -nworst 1 \
    -path_type full_clock_expanded -file ${prefix}_hold.rpt
report_clocks -file ${prefix}_clocks.rpt
report_exceptions -file ${prefix}_exceptions.rpt
close_design
