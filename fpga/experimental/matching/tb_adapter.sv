`timescale 1ns/1ps
module tb_adapter;
    logic clk = 0;
    always #5 clk = !clk;
    logic rst = 1, shot_abort = 0;
    logic cfg_begin = 0, cfg_write = 0, cfg_commit = 0;
    logic [15:0] cfg_detector_count = 24, cfg_edge_count = 78, cfg_observable_count = 1;
    logic [15:0] cfg_edge_index = 0, cfg_endpoint_a = 0, cfg_endpoint_b = 0;
    logic [31:0] cfg_observable_mask = 0;
    wire cfg_ack, cfg_error, configured;
    wire [15:0] detector_count, edge_count, observable_count;
    logic in_valid = 0, out_ready = 0;
    logic [23:0] syndrome = 0;
    wire in_ready, out_valid, decode_error;
    wire [0:0] prediction;
    wire [31:0] cycles;
    qec_decoder #(.MAX_DETECTORS(24), .MAX_EDGES(78), .MAX_OBSERVABLES(1)) dut (.*);
    integer g, f, parsed, i, j, count, a, b, o, expected, uf, err, truth, elapsed;
    logic [59:0] cost;
    logic [23:0] shot;
    task tick;
        @(posedge clk); #1;
    endtask
    task load(input bit poison);
        @(negedge clk); cfg_begin = 1;
        tick();
        if (!cfg_ack || cfg_error) $fatal(1, "begin failed");
        @(negedge clk); cfg_begin = 0;
        g = $fopen("../uf_graph.txt", "r");
        for (j = 0; j < 78; j = j + 1) begin
            parsed = $fscanf(g, "%d %d %d", a, b, o);
            if (parsed != 3) $fatal(1, "graph missing");
            cfg_edge_index = j; cfg_endpoint_a = a; cfg_endpoint_b = b;
            cfg_observable_mask = o ^ (poison && j == 10);
            cfg_write = 1; tick();
            if (!cfg_ack || cfg_error != (poison && j == 10)) $fatal(1, "edge identity check");
            @(negedge clk); cfg_write = 0;
        end
        $fclose(g);
        cfg_commit = 1; tick();
        if (!cfg_ack || cfg_error != poison || configured == poison) $fatal(1, "commit validation");
        @(negedge clk); cfg_commit = 0;
    endtask
    initial begin
        repeat(2) tick();
        @(negedge clk); rst = 0;
        load(1);
        if (in_ready) $fatal(1, "poison graph armed");
        load(0);
        f = $fopen("../vectors.txt", "r");
        parsed = $fscanf(f, "%d", count);
        if (parsed != 1 || count != 1050) $fatal(1, "vectors missing");
        for (i = 0; i < count; i = i + 1) begin
            parsed = $fscanf(f, "%h %h %d %d %d %d", shot, cost, expected, uf, err, truth);
            if (parsed != 6) $fatal(1, "vector missing");
            @(negedge clk); syndrome = shot; in_valid = 1;
            if (!in_ready) $fatal(1, "not ready");
            tick();
            @(negedge clk); in_valid = 0;
            elapsed = 0;
            while (!out_valid) begin
                tick(); elapsed = elapsed + 1;
                if (elapsed > 10000) $fatal(1, "timeout");
            end
            if (prediction != expected || dut.exact_cost != cost || cycles != elapsed || cycles > 1000 || (shot == 0 && cycles != 1) || decode_error)
                $fatal(1, "result/counter mismatch %0d", i);
            repeat(3) begin
                tick();
                if (!out_valid || cycles != elapsed || prediction != expected) $fatal(1, "held result");
            end
            @(negedge clk); out_ready = 1; tick();
            @(negedge clk); out_ready = 0;
        end
        // Abort must preserve graph validity and allow a fresh whole computation.
        in_valid = 1; tick();
        @(negedge clk); in_valid = 0;
        repeat(20) tick();
        @(negedge clk); shot_abort = 1; tick();
        @(negedge clk); shot_abort = 0; #1;
        if (!in_ready || out_valid || !configured) $fatal(1, "abort recovery");
        syndrome = 0; in_valid = 1; tick();
        @(negedge clk); in_valid = 0;
        while (!out_valid) tick();
        if (prediction || cycles != 1) $fatal(1, "post-abort decode");
        $display("PASS adapter: 1050 complete shots, independent counter, poisoned load recovery, abort, held results");
        $finish;
    end
endmodule
