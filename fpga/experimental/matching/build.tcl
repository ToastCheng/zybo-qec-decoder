# Experimental fixed matching image; maintained UF build remains unchanged.
# Build a fresh image with optional detector, edge and observable capacities.
set root [file normalize [file join [file dirname [info script]] .. .. ..]]
if {[llength $argv] > 4} {
    error "Usage: build.tcl ?new-output-dir? ?max-detectors? ?max-edges? ?max-observables?"
}
set output_arg [lindex $argv 0]
if {$output_arg eq ""} {
    set output_arg build/matching-board/image
}
set output_dir [file normalize [file join $root $output_arg]]
# Refuse protected paths and nonempty outputs rather than replacing artifacts.
set build_root [file join $root build]
if {$output_dir eq $root || $output_dir eq $build_root ||
    [string first "$output_dir/" "$root/"] == 0 ||
    ([string first "$root/" "$output_dir/"] == 0 &&
     [string first "$build_root/" "$output_dir/"] != 0)} {
    error "Output must be a new isolated build subdirectory or an external directory"
}
if {[file exists $output_dir] &&
    (![file isdirectory $output_dir] ||
     [llength [glob -nocomplain -directory $output_dir * .*]] > 2)} {
    error "Refusing existing nonempty output directory: $output_dir"
}
set capacities {24 78 1}
for {set index 0} {$index < 3} {incr index} {
    set value [lindex $argv [expr {$index + 1}]]
    if {$value ne ""} {
        lset capacities $index $value
    }
}
lassign $capacities max_detectors max_edges max_observables
foreach value $capacities maximum {65535 65535 32} {
    if {![string is integer -strict $value] || $value < 1 || $value > $maximum} {
        error "Invalid decoder capacity: $value (range 1..$maximum)"
    }
}
if {$capacities ne {24 78 1}} {error "Matching image is fixed at 24/78/1"}
if {[info exists ::env(QEC_BOARD_REPO)]} {
    set boards [file normalize [file join $root $::env(QEC_BOARD_REPO)]]
    if {![file isdirectory $boards]} {
        error "QEC_BOARD_REPO must name an existing board_files directory"
    }
    set_param board.repoPaths [list $boards]
} elseif {[info exists ::env(XILINX_VIVADO)]} {
    set boards [file normalize [file join $::env(XILINX_VIVADO) .. data boards board_files]]
    if {[file isdirectory $boards]} {
        set_param board.repoPaths [list $boards]
    }
}
file mkdir $output_dir
cd $output_dir
set proj_dir [file join $output_dir vivado_qec_soc]
create_project qec_soc $proj_dir -part xc7z010clg400-1
set_property board_part digilentinc.com:zybo-z7-10:part0:1.2 [current_project]
create_bd_design system
source [file join $root fpga scripts bd soc.tcl]
validate_bd_design
generate_target all [get_files system.bd]
set wrapper [make_wrapper -files [get_files system.bd] -top]
add_files -norecurse $wrapper
# Add only the decoder and mailbox sources.
set matching_dir [file join $root fpga experimental matching]
foreach source {adapter.sv ps_bridge.sv matching_exact.sv} {
    add_files -norecurse [file join $matching_dir $source]
}
set_property include_dirs [list $matching_dir] [current_fileset]
add_files -norecurse [file join $root fpga rtl top top_qec_soc.sv]
add_files -fileset constrs_1 -norecurse [file join $root fpga constraints top_qec_soc.xdc]
set_property top top_qec_soc [current_fileset]
set_property generic [list MAX_DETECTORS=$max_detectors MAX_EDGES=$max_edges MAX_OBSERVABLES=$max_observables] [current_fileset]
set_property strategy Performance_ExplorePostRoutePhysOpt [get_runs impl_1]
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {
    error "Decoder implementation failed; inspect $proj_dir/qec_soc.runs/impl_1"
}
open_run impl_1
report_utilization -file [file join $output_dir qec_soc_utilization.rpt]
report_timing_summary -delay_type min_max -report_unconstrained \
    -file [file join $output_dir qec_soc_timing_summary.rpt]
report_drc -file [file join $output_dir qec_soc_drc.rpt]
# Require routed setup and hold paths before exporting an image.
foreach delay_type {max min} {
    set paths [get_timing_paths -delay_type $delay_type -max_paths 1]
    if {[llength $paths] == 0} {
        error "Decoder image has no routed $delay_type timing paths"
    }
    set slack [get_property SLACK [lindex $paths 0]]
    if {![string is double -strict $slack] || $slack < 0} {
        error "Decoder image fails routed $delay_type timing: $slack"
    }
}
file copy [file join $proj_dir qec_soc.runs impl_1 top_qec_soc.bit] \
    [file join $output_dir qec_soc.bit]
write_hw_platform -fixed -include_bit [file join $output_dir qec_soc.xsa]
puts "Build complete: $output_dir/qec_soc.bit and $output_dir/qec_soc.xsa"
