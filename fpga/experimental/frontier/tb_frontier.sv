`timescale 1ns/1ps
// Testbench for the programmable parity-frontier qec_decoder.
// Checks poisoned-upload rejection, hardware program CRC, exact costs,
// predictions, cycle counts, and output hold stability across miniature,
// real d3, and real d5 programs, plus mid-decode shot_abort recovery.
module tb_frontier;
    logic clk = 0;
    always #5 clk = !clk;
    logic rst = 1, shot_abort = 0;
    logic cfg_begin = 0, cfg_write = 0, cfg_commit = 0;
    logic [15:0] cfg_detector_count = 0, cfg_edge_count = 0, cfg_observable_count = 1;
    logic [15:0] cfg_edge_index = 0, cfg_endpoint_a = 0, cfg_endpoint_b = 0;
    logic [31:0] cfg_observable_mask = 0;
    wire cfg_ack, cfg_error, configured;
    wire [15:0] detector_count, edge_count, observable_count;
    logic in_valid = 0, out_ready = 0;
    logic [127:0] syndrome = 0;
    wire in_ready, out_valid, decode_error;
    wire [0:0] prediction;
    wire [31:0] cycles, program_crc;
    qec_decoder dut (.*);
    integer f, g, count, shots, program_index, i, parsed, expected, elapsed, timeout_count;
    logic [15:0] a, b;
    logic [63:0] weight, expected_cost;
    logic [71:0] shot;
    logic [31:0] expected_crc;
    // Advance one clock and sample 1 ns later so DUT register updates settle.
    task tick;
        @(posedge clk); #1;
    endtask
    // Wait for cfg_ack (allowing for the 10-cycle per-record CRC pass) and
    // verify cfg_error matches expect_error.
    task wait_cfg(input bit expect_error);
        timeout_count = 0;
        while (!cfg_ack) begin
            tick(); timeout_count = timeout_count + 1;
            if (timeout_count > 100) $fatal(1, "configuration timeout");
        end
        if (cfg_error != expect_error) $fatal(1, "unexpected cfg_error=%0d want=%0d", cfg_error, expect_error);
    endtask
    // Upload count DP operations from handle (two cfg_write records per op for
    // the 64-bit weight), commit, verify program_crc, and replay vectors shots
    // checking exact cost, prediction, cycle count, and held output stability.
    task run_program(input integer handle, input integer vectors, input bit hex_syndrome);
        for (i = 0; i < count; i = i + 1) begin
            parsed = $fscanf(handle, "%h %h %h", a, b, weight);
            if (parsed != 3) $fatal(1, "bad operation");
            @(negedge clk);
            cfg_edge_index = 2*i; cfg_endpoint_a = a; cfg_endpoint_b = b;
            cfg_observable_mask = weight[31:0]; cfg_write = 1;
            tick(); @(negedge clk); cfg_write = 0; wait_cfg(0);
            @(negedge clk);
            cfg_edge_index = 2*i+1;
            cfg_observable_mask = weight[63:32]; cfg_write = 1;
            tick(); @(negedge clk); cfg_write = 0; wait_cfg(0);
        end
        @(negedge clk); cfg_commit = 1; tick(); @(negedge clk); cfg_commit = 0; wait_cfg(0);
        if (!configured || program_crc != expected_crc) $fatal(1, "program CRC mismatch %h %h", program_crc, expected_crc);
        for (i = 0; i < vectors; i = i + 1) begin
            parsed = hex_syndrome ? $fscanf(handle, "%h %h %d", shot, expected_cost, expected)
                                  : $fscanf(handle, "%d %h %d", shot, expected_cost, expected);
            if (parsed != 3) $fatal(1, "missing truth");
            @(negedge clk); syndrome = shot; in_valid = 1;
            if (!in_ready) $fatal(1, "not ready");
            tick(); @(negedge clk); in_valid = 0;
            elapsed = 0;
            while (!out_valid) begin
                tick(); elapsed = elapsed + 1;
                if (elapsed > 3000000) $fatal(1, "decode timeout");
            end
            if (decode_error || prediction != expected || dut.result_cost != expected_cost || cycles != elapsed)
                $fatal(1, "bad exact result s=%h p=%0d want=%0d cost=%h want=%h cycles=%0d elapsed=%0d", shot, prediction, expected, dut.result_cost, expected_cost, cycles, elapsed);
            if (i < 2 && hex_syndrome)
                $display("OBSERVED det=%0d shot=%h cycles=%0d", cfg_detector_count, shot, cycles);
            repeat(3) begin
                tick();
                if (!out_valid || prediction != expected || cycles != elapsed) $fatal(1, "held result changed");
            end
            @(negedge clk); out_ready = 1; tick(); @(negedge clk); out_ready = 0;
        end
    endtask
    initial begin
        repeat(2) tick();
        @(negedge clk); rst = 0;
        // A zero-mask record must fail write and poison commit, leaving decode disarmed.
        cfg_detector_count = 3; cfg_edge_count = 2; cfg_begin = 1;
        tick(); @(negedge clk); cfg_begin = 0; wait_cfg(0);
        cfg_edge_index = 0; cfg_endpoint_a = 0; cfg_endpoint_b = 0; cfg_observable_mask = 1;
        cfg_write = 1; tick(); @(negedge clk); cfg_write = 0; wait_cfg(1);
        cfg_commit = 1; tick(); @(negedge clk); cfg_commit = 0; wait_cfg(1);
        if (configured || in_ready) $fatal(1, "poisoned load armed");

        f = $fopen("../mini-program.txt", "r");
        parsed = $fscanf(f, "%d %d %h", cfg_detector_count, count, expected_crc);
        if (parsed != 3) $fatal(1, "missing mini program");
        cfg_edge_count = 2*count;
        @(negedge clk); cfg_begin = 1; tick(); @(negedge clk); cfg_begin = 0; wait_cfg(0);
        run_program(f, 8, 0);
        $fclose(f);

        g = $fopen("../real-d3-d5-programs.txt", "r");
        for (program_index = 0; program_index < 2; program_index = program_index + 1) begin
            parsed = $fscanf(g, "%d %d %h %d", cfg_detector_count, count, expected_crc, shots);
            if (parsed != 4) $fatal(1, "missing real program");
            cfg_edge_count = 2*count;
            @(negedge clk); cfg_begin = 1; tick(); @(negedge clk); cfg_begin = 0; wait_cfg(0);
            run_program(g, shots, 1);
        end
        $fclose(g);
        // Abort an in-flight all-ones d5 decode; the loaded program must stay configured.
        @(negedge clk); syndrome = 72'hffffffffffffffffff; in_valid = 1;
        tick(); @(negedge clk); in_valid = 0;
        repeat(40) tick();
        @(negedge clk); shot_abort = 1; tick(); @(negedge clk); shot_abort = 0; #1;
        if (!configured || !in_ready || out_valid) $fatal(1, "abort recovery failed");
        syndrome = 0; in_valid = 1; tick(); @(negedge clk); in_valid = 0;
        while (!out_valid) tick();
        if (prediction || cycles != 1 || decode_error) $fatal(1, "post-abort zero shot");
        $display("PASS programmable exact frontier: miniature, real d3 and real d5 programs, all-one d5, poisoned recovery and shot abort");
        $finish;
    end
endmodule
