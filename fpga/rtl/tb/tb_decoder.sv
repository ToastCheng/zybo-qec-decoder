`timescale 1ns / 1ps
module tb_decoder;
    logic clk = 0;
    always #5 clk = !clk;
    logic rst = 1;
    logic shot_abort = 0;
    logic cfg_begin = 0;
    logic cfg_write = 0;
    logic cfg_commit = 0;
    logic [15:0] cfg_detector_count = 1;
    logic [15:0] cfg_edge_count = 1;
    logic [15:0] cfg_observable_count = 32;
    logic [15:0] cfg_edge_index = 0;
    logic [15:0] cfg_endpoint_a = 0;
    logic [15:0] cfg_endpoint_b = 1;
    logic [31:0] cfg_observable_mask = 32'h80000005;
    wire cfg_ack;
    wire cfg_error;
    wire configured;
    wire [15:0] detector_count;
    wire [15:0] edge_count;
    wire [15:0] observable_count;
    logic in_valid = 0;
    logic out_ready = 0;
    logic [127:0] syndrome = 0;
    wire in_ready;
    wire out_valid;
    wire decode_error;
    wire [31:0] prediction;
    wire [31:0] cycles;
    integer fd, parsed, graphs, g, n, m, o, shots, e, s, a, b, expected_error;
    integer total = 0;
    logic [31:0] maximum_cycles = 0;
    logic [31:0] mask, expected_prediction;
    logic [127:0] shot;
    qec_decoder dut (.*);
    wire parameters_done;
    qec_parameter_probe parameter_probe (.done(parameters_done));

    task tick;
        @(posedge clk);
        #1;
    endtask
    task configuration_command(input integer op, input bit expect_error);
        @(negedge clk);
        cfg_begin = op == 1;
        cfg_write = op == 2;
        cfg_commit = op == 3;
        tick();
        if (!cfg_ack || cfg_error !== expect_error) begin
            $fatal(1, "config op=%0d error=%b expected=%b", op, cfg_error, expect_error);
        end
        @(negedge clk);
        cfg_begin = 0;
        cfg_write = 0;
        cfg_commit = 0;
    endtask
    task begin_graph(input integer detectors, input integer edges, input integer observables, input bit bad);
        cfg_detector_count = 16'(detectors);
        cfg_edge_count = 16'(edges);
        cfg_observable_count = 16'(observables);
        configuration_command(1, bad);
        if (configured || in_ready) $fatal(1, "begin did not invalidate");
    endtask
    task append(input integer index, input integer endpoint_a, input integer endpoint_b, input logic [31:0] obs, input bit bad);
        cfg_edge_index = 16'(index);
        cfg_endpoint_a = 16'(endpoint_a);
        cfg_endpoint_b = 16'(endpoint_b);
        cfg_observable_mask = obs;
        configuration_command(2, bad);
    endtask
    task one_graph;
        begin_graph(1, 1, 32, 0);
        append(0, 0, 1, 32'h80000005, 0);
        configuration_command(3, 0);
    endtask
    task launch(input logic [127:0] value);
        @(negedge clk);
        if (!in_ready) $fatal(1, "not ready to launch");
        syndrome = value;
        in_valid = 1;
        tick();
        @(negedge clk);
        in_valid = 0;
    endtask
    task retire;
        @(negedge clk);
        out_ready = 1;
        tick();
        @(negedge clk);
        out_ready = 0;
        if (!in_ready || out_valid) $fatal(1, "did not retire");
    endtask
    task check_shot(input logic [127:0] value, input logic [31:0] expected, input bit error_expected);
        integer elapsed;
        logic [31:0] held_cycles;
        launch(value);
        elapsed = 0;
        while (!out_valid) begin
            tick();
            elapsed = elapsed + 1;
            if (elapsed > 1000000) $fatal(1, "algorithm timeout");
        end
        if (prediction !== expected || decode_error !== error_expected) begin
            $fatal(1, "g=%0d syndrome=%h prediction=%h expected=%h error=%b expected=%b",
                g, value, prediction, expected, decode_error, error_expected);
        end
        if (cycles !== 32'(elapsed)) $fatal(1, "cycles=%0d measured=%0d", cycles, elapsed);
        held_cycles = cycles;
        if (cycles > maximum_cycles) maximum_cycles = cycles;
        // Stall the result while presenting an input that must not be accepted.
        @(negedge clk);
        in_valid = 1;
        syndrome = ~value;
        repeat (3) begin
            tick();
            if (in_ready || !out_valid || prediction !== expected
                || decode_error !== error_expected || cycles !== held_cycles) begin
                $fatal(1, "result changed under backpressure");
            end
        end
        @(negedge clk);
        in_valid = 0;
        retire();
        total = total + 1;
    endtask
    initial begin
        repeat (2) tick();
        @(negedge clk);
        rst = 0;
        if (in_ready || configured) $fatal(1, "full reset configured a graph");
        // An abort cannot repair a poisoned graph load.
        begin_graph(129, 1, 1, 1);
        configuration_command(3, 1);
        begin_graph(1, 513, 1, 1);
        configuration_command(3, 1);
        begin_graph(1, 1, 33, 1);
        configuration_command(3, 1);
        begin_graph(1, 1, 1, 0);
        configuration_command(3, 1);
        append(0, 0, 1, 1, 1);
        begin_graph(1, 1, 1, 0);
        append(1, 0, 1, 1, 1);
        configuration_command(3, 1);
        begin_graph(1, 1, 1, 0);
        append(0, 0, 2, 1, 1);
        configuration_command(3, 1);
        begin_graph(1, 1, 1, 0);
        append(0, 1, 1, 1, 1);
        configuration_command(3, 1);
        begin_graph(1, 1, 1, 0);
        append(0, 0, 1, 2, 1);
        configuration_command(3, 1);
        begin_graph(1, 1, 1, 0);
        append(0, 0, 1, 1, 0);
        @(negedge clk);
        cfg_write = 1;
        cfg_commit = 1;
        tick();
        if (!cfg_ack || !cfg_error) $fatal(1, "simultaneous config command not rejected");
        @(negedge clk);
        cfg_write = 0;
        cfg_commit = 0;
        configuration_command(3, 1);
        begin_graph(1, 1, 1, 0);
        append(0, 0, 1, 1, 0);
        append(0, 0, 1, 1, 1);
        configuration_command(3, 1);
        if (configured || in_ready) $fatal(1, "invalid load did not fail closed");
        one_graph();
        // Append and commit require a preceding begin.
        append(0, 0, 1, 0, 1);
        configuration_command(3, 1);
        check_shot(1, 32'h80000005, 0);
        check_shot(128'h80000000000000000000000000000000, 0, 1);
        // Configuration rejection must preserve an active shot or held result.
        launch(1);
        configuration_command(1, 1);
        configuration_command(2, 1);
        configuration_command(3, 1);
        while (!out_valid) tick();
        configuration_command(1, 1);
        configuration_command(2, 1);
        configuration_command(3, 1);
        if (prediction !== 32'h80000005 || decode_error || !configured) $fatal(1, "busy config changed graph");
        retire();
        // Abort discards the shot, not the committed graph.
        launch(1);
        repeat (3) tick();
        @(negedge clk);
        shot_abort = 1;
        tick();
        @(negedge clk);
        shot_abort = 0;
        #1;
        if (!configured || !in_ready || out_valid || cycles != 0) $fatal(1, "shot abort lost graph");
        check_shot(1, 32'h80000005, 0);
        launch(1);
        while (!out_valid) tick();
        @(negedge clk);
        shot_abort = 1;
        tick();
        @(negedge clk);
        shot_abort = 0;
        check_shot(0, 0, 0);
        // Reload every corpus graph without elaborating another decoder.
        fd = $fopen("qec_vectors.txt", "r");
        if (!fd) $fatal(1, "missing generated reference vectors");
        parsed = $fscanf(fd, "%d\n", graphs);
        if (parsed != 1) $fatal(1, "bad corpus header");
        for (g = 0; g < graphs; g = g + 1) begin
            parsed = $fscanf(fd, "%d %d %d %d\n", n, m, o, shots);
            if (parsed != 4) $fatal(1, "bad graph header");
            begin_graph(n, m, o, 0);
            for (e = 0; e < m; e = e + 1) begin
                parsed = $fscanf(fd, "%d %d %h\n", a, b, mask);
                if (parsed != 3) $fatal(1, "bad edge record");
                append(e, a, b, mask, 0);
            end
            configuration_command(3, 0);
            if (!configured || detector_count != n || edge_count != m || observable_count != o) $fatal(1, "wrong dimensions");
            for (s = 0; s < shots; s = s + 1) begin
                parsed = $fscanf(fd, "%h %h %d\n", shot, expected_prediction, expected_error);
                if (parsed != 3) $fatal(1, "bad shot record");
                check_shot(shot, expected_prediction, 1'(expected_error));
            end
            $display("graph=%0d detectors=%0d edges=%0d observables=%0d shots=%0d", g, n, m, o, shots);
        end
        $fclose(fd);
        @(negedge clk);
        rst = 1;
        tick();
        @(negedge clk);
        rst = 0;
        if (configured || in_ready || out_valid) $fatal(1, "full reset preserved graph");
        one_graph();
        check_shot(1, 32'h80000005, 0);
        if (!parameters_done) $fatal(1, "minimal parameter probe did not finish");
        if (maximum_cycles <= 65535) $fatal(1, "corpus failed to cross 16-bit cycle boundary");
        $display("PASS qec core graphs=%0d checked_shots=%0d maximum_cycles=%0d config recovery stalls abort reset cycles", graphs, total, maximum_cycles);
        $finish;
    end
    initial begin
        #1000000000;
        $fatal(1, "timeout");
    end
endmodule

// Check declaration widths at the smallest supported capacities.
module qec_parameter_probe(output logic done = 0);
    logic clk = 0;
    always #5 clk = !clk;
    logic rst = 1;
    logic shot_abort = 0;
    logic cfg_begin = 0;
    logic cfg_write = 0;
    logic cfg_commit = 0;
    logic [15:0] cfg_detector_count = 1;
    logic [15:0] cfg_edge_count = 1;
    logic [15:0] cfg_observable_count = 1;
    logic [15:0] cfg_edge_index = 0;
    logic [15:0] cfg_endpoint_a = 0;
    logic [15:0] cfg_endpoint_b = 1;
    logic [31:0] cfg_observable_mask = 1;
    wire cfg_ack, cfg_error, configured;
    wire [15:0] detector_count, edge_count, observable_count;
    logic in_valid = 0;
    logic out_ready = 0;
    logic [0:0] syndrome = 1;
    wire in_ready, out_valid, decode_error;
    wire [0:0] prediction;
    wire [31:0] cycles;
    integer elapsed;
    qec_decoder #(
        .MAX_DETECTORS(1), .MAX_EDGES(1), .MAX_OBSERVABLES(1)
    ) dut (.*);
    initial begin
        repeat (2) @(negedge clk);
        rst = 0;
        cfg_begin = 1;
        @(negedge clk);
        if (!cfg_ack || cfg_error) $fatal(1, "minimal begin failed");
        cfg_begin = 0;
        cfg_write = 1;
        @(negedge clk);
        if (!cfg_ack || cfg_error) $fatal(1, "minimal append failed");
        cfg_write = 0;
        cfg_commit = 1;
        @(negedge clk);
        if (!cfg_ack || cfg_error || !configured) $fatal(1, "minimal commit failed");
        cfg_commit = 0;
        @(negedge clk);
        in_valid = 1;
        @(negedge clk);
        in_valid = 0;
        elapsed = 0;
        while (!out_valid) begin
            @(negedge clk);
            elapsed = elapsed + 1;
        end
        if (decode_error || prediction !== 1'b1 || cycles != elapsed) $fatal(1, "minimal decode failed");
        out_ready = 1;
        @(negedge clk);
        out_ready = 0;
        cfg_observable_count = 2;
        cfg_begin = 1;
        @(negedge clk);
        if (!cfg_ack || !cfg_error || configured) $fatal(1, "minimal observable capacity failed");
        cfg_begin = 0;
        done = 1;
    end
endmodule
