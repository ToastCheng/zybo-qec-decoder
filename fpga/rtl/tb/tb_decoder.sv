`timescale 1ns / 1ps
// Core testbench for qec_decoder.
//
// What is verified
// ----------------
// 1. Configuration validation: rejects over-capacity dimensions, out-of-order
//    or duplicate edge indices, invalid/self-loop endpoints, over-wide
//    observable masks, simultaneous cfg strobes, and commits after a bad load.
// 2. Handshake & isolation: measures unblocked back-to-back initiation interval
//    (`initiation.csv`), stalls output under backpressure while checking output
//    stability, confirms busy/held config rejections keep active state intact,
//    and contrasts graph-preserving `shot_abort` with full `rst`.
// 3. Multi-graph vector replay: reloads every graph from `qec_vectors.txt` into
//    one elaborated instance, checks predictions/errors/cycle counts, logs per-
//    state cycle counts (`profile.csv`) and ordered merge/peel events
//    (`trace.csv`), and verifies the corpus crosses the 16-bit cycle boundary.
// 4. Minimal capacities: `qec_parameter_probe` checks width edge cases at 1/1/1.
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
    integer profile_fd, trace_fd;
    integer state_cycles [0:16];
    integer total = 0;
    logic [31:0] maximum_cycles = 0;
    logic [31:0] mask, expected_prediction;
    logic [127:0] shot;
    qec_decoder dut (.*);
    wire parameters_done;
    qec_parameter_probe parameter_probe (.done(parameters_done));

    // Advance to one time unit past posedge clk so nonblocking DUT updates settle.
    task tick;
        @(posedge clk);
        #1;
    endtask
    // Pulse one configuration strobe (1=begin, 2=write, 3=commit) on negedge
    // and assert cfg_ack and cfg_error on the following posedge.
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
    // Start a graph upload and confirm decoding is immediately disarmed,
    // even when the requested dimensions are rejected.
    task begin_graph(input integer detectors, input integer edges, input integer observables, input bit bad);
        cfg_detector_count = 16'(detectors);
        cfg_edge_count = 16'(edges);
        cfg_observable_count = 16'(observables);
        configuration_command(1, bad);
        if (configured || in_ready) $fatal(1, "begin did not invalidate");
    endtask
    // Submit one edge record (index, endpoints, observable mask); bad=1 expects rejection.
    task append(input integer index, input integer endpoint_a, input integer endpoint_b, input logic [31:0] obs, input bit bad);
        cfg_edge_index = 16'(index);
        cfg_endpoint_a = 16'(endpoint_a);
        cfg_endpoint_b = 16'(endpoint_b);
        cfg_observable_mask = obs;
        configuration_command(2, bad);
    endtask
    // Load a 1-detector, 1-edge boundary graph with mask 0x80000005 (tests bit 31 and low bits).
    task one_graph;
        begin_graph(1, 1, 32, 0);
        append(0, 0, 1, 32'h80000005, 0);
        configuration_command(3, 0);
    endtask
    // Assert in_ready and present one syndrome for a single acceptance edge.
    task launch(input logic [127:0] value);
        @(negedge clk);
        if (!in_ready) $fatal(1, "not ready to launch");
        syndrome = value;
        in_valid = 1;
        tick();
        @(negedge clk);
        in_valid = 0;
    endtask
    // Pulse out_ready to retire a held result and confirm the core returns to IDLE.
    task retire;
        @(negedge clk);
        out_ready = 1;
        tick();
        @(negedge clk);
        out_ready = 0;
        if (!in_ready || out_valid) $fatal(1, "did not retire");
    endtask
    // Hold in_valid and out_ready high continuously to measure back-to-back
    // initiation interval directly (expected: latency + 2 cycles for HOLD/IDLE).
    task check_initiation;
        integer edge_number, accepted, completed, last_accept, last_result;
        integer last_latency, initiation_fd;
        bit accepting;
        bit was_valid;
        initiation_fd = $fopen("initiation.csv", "w");
        $fwrite(initiation_fd, "previous_syndrome,latency,acceptance_gap\n");
        edge_number = 0;
        accepted = 0;
        completed = 0;
        last_accept = 0;
        last_result = 0;
        last_latency = 0;
        @(negedge clk);
        in_valid = 1;
        out_ready = 1;
        syndrome = 0;
        while (completed < 4) begin
            @(posedge clk);
            edge_number = edge_number + 1;
            accepting = in_valid && in_ready;
            was_valid = out_valid;
            if (accepting) begin
                if (accepted > 0) begin
                    if (edge_number - last_accept != last_latency + 2)
                        $fatal(1, "unexpected unblocked initiation interval");
                    $fwrite(initiation_fd, "%0d,%0d,%0d\n", (accepted - 1) % 2, last_latency, edge_number - last_accept);
                end
                last_accept = edge_number;
                accepted = accepted + 1;
            end
            #1;
            if (out_valid && !was_valid) begin
                last_result = edge_number;
                last_latency = last_result - last_accept;
                if (cycles != last_latency || decode_error
                    || prediction != ((completed % 2) ? 32'h80000005 : 0))
                    $fatal(1, "unblocked result differs from independent edges");
                completed = completed + 1;
            end
            @(negedge clk);
            if (accepting) syndrome = 128'(accepted % 2);
            if (accepted == 4) in_valid = 0;
        end
        tick();
        @(negedge clk);
        out_ready = 0;
        in_valid = 0;
        if (!in_ready || out_valid) $fatal(1, "unblocked retirement failed");
        $fclose(initiation_fd);
    endtask
    // Run one shot, verify prediction/error/cycle count, log profile + merge/peel
    // trace rows, hold output under backpressure for 3 cycles, then retire it.
    task check_shot(input logic [127:0] value, input logic [31:0] expected, input bit error_expected);
        integer elapsed;
        integer i;
        logic [31:0] held_cycles;
        launch(value);
        elapsed = 0;
        for (i = 0; i < 17; i = i + 1) state_cycles[i] = 0;
        while (!out_valid) begin
            state_cycles[dut.state] = state_cycles[dut.state] + 1;
            // Record exact merge (GROW_APPLY=7) and peel (FIND_APPLY=14) events so
            // tie-breaking regressions are caught even if final observables match.
            if (dut.state == 7 && dut.roots_differ && dut.expanded >= 2)
                $fwrite(trace_fd, "%0d,%0d,merge,%0d,%0d,%0d\n", g, s, dut.edge_cursor, dut.winner, dut.loser);
            if (dut.state == 14 && dut.edge_forest && (dut.a == dut.leaf || dut.b == dut.leaf))
                $fwrite(trace_fd, "%0d,%0d,peel,%0d,%0d,%0d\n", g, s, dut.edge_cursor, dut.leaf, dut.leaf_work);
            tick();
            elapsed = elapsed + 1;
            if (elapsed > 1000000) $fatal(1, "algorithm timeout");
        end
        if (prediction !== expected || decode_error !== error_expected) begin
            $fatal(1, "g=%0d syndrome=%h prediction=%h expected=%h error=%b expected=%b",
                g, value, prediction, expected, decode_error, error_expected);
        end
        if (cycles !== 32'(elapsed)) $fatal(1, "cycles=%0d measured=%0d", cycles, elapsed);
        $fwrite(profile_fd, "%0d,%0d,%032h,%08h,%0d,%0d", g, s, value, prediction, decode_error, elapsed);
        for (i = 0; i < 17; i = i + 1) $fwrite(profile_fd, ",%0d", state_cycles[i]);
        $fwrite(profile_fd, "\n");
        held_cycles = cycles;
        if (cycles > maximum_cycles) maximum_cycles = cycles;
        // Hold out_ready low while presenting another syndrome; outputs must stay
        // frozen and in_ready must remain low until the held result is retired.
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
        profile_fd = $fopen("profile.csv", "w");
        trace_fd = $fopen("trace.csv", "w");
        $fwrite(trace_fd, "graph,shot,event,edge,vertex_or_winner,work_or_loser\n");
        $fwrite(profile_fd, "graph,shot,syndrome,prediction,error,cycles,IDLE,INIT,CHECK,GROW,GROW_ROOTS,GROW_VALUES,GROW_SELECT,GROW_APPLY,RELABEL,ADVANCE,LEAVES,FIND,FIND_VALUES,FIND_OTHER,FIND_APPLY,VERIFY,HOLD\n");
        // Tag pre-corpus protocol diagnostics as graph -1 / shot -1 in CSV outputs.
        g = -1;
        s = -1;
        repeat (2) tick();
        @(negedge clk);
        rst = 0;
        if (in_ready || configured) $fatal(1, "full reset configured a graph");
        // Phase 1: negative configuration tests (over-capacity, short write, bad index,
        // out-of-range endpoint, self-loop, over-wide mask, simultaneous strobes, extra edge).
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
        // Phase 2: commit a valid 1-detector graph, check unblocked initiation interval,
        // stray append/commit rejection, normal decode, and out-of-range syndrome bit rejection.
        one_graph();
        check_initiation();
        append(0, 0, 1, 0, 1);
        configuration_command(3, 1);
        check_shot(1, 32'h80000005, 0);
        check_shot(128'h80000000000000000000000000000000, 0, 1);
        // Phase 3: config requests arriving mid-decode or during HOLD must error
        // without corrupting the active shot, held result, or committed graph.
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
        // Phase 4: shot_abort mid-decode and during HOLD cancels only the shot, keeping the graph.
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
        // Phase 5: replay every graph and shot in qec_vectors.txt without re-elaborating.
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
        // Phase 6: full reset must clear the committed graph; verify clean reload afterward.
        @(negedge clk);
        rst = 1;
        tick();
        @(negedge clk);
        rst = 0;
        if (configured || in_ready || out_valid) $fatal(1, "full reset preserved graph");
        one_graph();
        check_shot(1, 32'h80000005, 0);
        if (!parameters_done) $fatal(1, "minimal parameter probe did not finish");
        if (!$test$plusargs("profile_only") && maximum_cycles <= 65535)
            $fatal(1, "corpus failed to cross 16-bit cycle boundary");
        $fclose(profile_fd);
        $fclose(trace_fd);
        $display("PASS qec core graphs=%0d checked_shots=%0d maximum_cycles=%0d config recovery stalls abort reset cycles", graphs, total, maximum_cycles);
        $finish;
    end
    initial begin
        #1000000000;
        $fatal(1, "timeout");
    end
endmodule

// Parameter-edge probe: instantiate qec_decoder at its minimum capacities (1/1/1)
// to catch any zero-width or bit-slice regressions in parameter expressions.
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
