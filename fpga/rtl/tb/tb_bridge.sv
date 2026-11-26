`timescale 1ns / 1ps
// Mailbox testbench for ps_bridge (instantiated with 20 detectors, 16 edges,
// 32 observables to exercise multi-word syndromes without long sim times).
//
// Verifies:
// - Metadata identity/capacity readback and out-of-range opcode/index rejection
// - Graph upload, generation increments, and isolation after a failed reload
// - Syndrome word bounds, padding-bit checks, and per-shot fresh-write rules
// - Status/DONE stability, 32-bit prediction readback, and shot abort
// - Recovery after a disconnected-graph decode error and after full reset
module tb_bridge;
    logic clk = 0;
    always #5 clk = !clk;
    logic rst = 1;
    logic [31:0] ctrl = 0;
    wire [31:0] status;
    integer i;
    logic [31:0] saved;
    ps_bridge #(
        .MAX_DETECTORS(20), .MAX_EDGES(16), .MAX_OBSERVABLES(32)
    ) dut (.*);
    // Advance to one time unit past posedge clk so nonblocking DUT updates settle.
    task tick;
        @(posedge clk);
        #1;
    endtask
    // Flip ctrl.REQ with (op, idx, data), wait for status.ACK to match, and
    // verify status.ERROR against error_expected.
    task command(input integer op, input integer idx, input integer data, input bit error_expected);
        @(negedge clk);
        ctrl = {~ctrl[31], 3'b0, 4'(op), 8'(idx), 16'(data)};
        tick();
        i = 0;
        while (status[31] != ctrl[31]) begin
            tick();
            i = i + 1;
            if (i > 20000) $fatal(1, "mailbox ack timeout op=%0d", op);
        end
        if (status[29] !== error_expected) $fatal(1, "mailbox error op=%0d status=%h", op, status);
    endtask
    // Issue metadata read (op 7) for `idx` and check the 16-bit READ_DATA value.
    task metadata(input integer idx, input integer expected);
        command(7, idx, 0, 0);
        if (status[15:0] !== 16'(expected)) $fatal(1, "metadata %0d got=%h expected=%h", idx, status[15:0], expected);
    endtask
    // Write one 16-bit staging register (op 1) and require a clean ack.
    task stage(input integer idx, input integer data);
        command(1, idx, data, 0);
    endtask
    // Upload a 1-detector boundary graph with mask 0x80000005 (spans both
    // 16-bit prediction metadata registers, indices 10 and 11).
    task load_graph;
        stage(0, 1);
        stage(1, 1);
        stage(2, 32);
        command(2, 0, 0, 0);
        stage(3, 0);
        stage(4, 0);
        stage(5, 1);
        stage(6, 5);
        stage(7, 16'h8000);
        command(3, 0, 0, 0);
        command(4, 0, 0, 0);
    endtask
    initial begin
        repeat (2) tick();
        @(negedge clk);
        rst = 0;
        // 1. Check version/capacities and reject invalid ops/indices before configuration.
        metadata(0, 2);
        metadata(1, 20);
        metadata(2, 16);
        metadata(3, 32);
        metadata(7, 0);
        command(6, 0, 0, 1);
        command(1, 8, 0, 1);
        command(7, 15, 0, 1);
        command(9, 0, 0, 1);
        stage(0, 21);
        command(2, 0, 0, 1);
        command(4, 0, 0, 1);
        metadata(7, 0);
        // 2. Load the 1-detector graph, check strict INDEX==0 enforcement and metadata.
        load_graph();
        metadata(8, 1);
        command(2, 1, 0, 1); // Nonzero index must error on index-free opcodes.
        command(3, 1, 0, 1);
        command(4, 1, 0, 1);
        command(6, 1, 0, 1);
        command(8, 1, 0, 1);
        metadata(7, 1);
        metadata(4, 1);
        metadata(5, 1);
        metadata(6, 32);
        // 3. Validate syndrome bounds/padding, run a decode, check DONE and readback.
        command(6, 0, 0, 1); // Reject decode before active syndrome words are written.
        command(5, 1, 0, 1); // Reject syndrome word index past configured detectors.
        command(5, 0, 2, 1); // Reject nonzero padding bits above detector_count.
        command(5, 0, 1, 0);
        command(6, 0, 0, 0);
        if (!status[30]) $fatal(1, "missing completion bit");
        saved = status;
        repeat (5) tick();
        if (status !== saved) $fatal(1, "status not stable");
        metadata(10, 5);
        metadata(11, 16'h8000);
        metadata(12, 31);
        metadata(13, 0);
        metadata(14, 0);
        // 4. Shot abort clears cached results and written_words while keeping the graph.
        command(8, 0, 0, 0);
        metadata(7, 1);
        metadata(8, 1);
        metadata(10, 0);
        command(6, 0, 0, 1);
        command(5, 0, 0, 0);
        command(6, 0, 0, 0);
        metadata(10, 0);
        // 5. A failed reload must disarm decoding rather than falling back to the old graph.
        command(2, 0, 0, 0);
        command(4, 0, 0, 1);
        metadata(7, 0);
        command(6, 0, 0, 1);
        load_graph();
        metadata(8, 2);
        command(5, 0, 1, 0);
        command(6, 0, 0, 0);
        metadata(11, 16'h8000);
        // 6. Reload a 17-detector graph (two 16-bit syndrome words, 1 active bit in word 1)
        //    and check fresh-word enforcement across shots.
        stage(0, 17);
        stage(1, 2);
        stage(2, 32);
        command(2, 0, 0, 0);
        stage(3, 0);
        stage(4, 0);
        stage(5, 17);
        stage(6, 3);
        stage(7, 0);
        command(3, 0, 0, 0);
        stage(3, 1);
        stage(4, 16);
        stage(6, 0);
        stage(7, 16'h8000);
        command(3, 0, 0, 0);
        command(4, 0, 0, 0);
        metadata(8, 3);
        metadata(4, 17);
        metadata(5, 2);
        command(5, 0, 1, 0);
        command(6, 0, 0, 1);
        command(5, 2, 0, 1);
        command(5, 1, 2, 1);
        command(5, 1, 1, 0);
        command(6, 0, 0, 0);
        metadata(10, 3);
        metadata(11, 16'h8000);
        command(6, 0, 0, 1); // Next shot must rewrite all active syndrome words.
        command(8, 0, 0, 0);
        metadata(7, 1);
        metadata(8, 3);
        command(5, 0, 1, 0);
        command(5, 1, 0, 0);
        command(6, 0, 0, 0);
        metadata(10, 3);
        metadata(11, 0);
        // 7. Disconnected 0-edge graph: odd syndrome must set DONE=1 and ERROR=1
        //    (saved_error=1), and a subsequent zero syndrome must recover cleanly.
        stage(0, 1);
        stage(1, 0);
        stage(2, 0);
        command(2, 0, 0, 0);
        command(4, 0, 0, 0);
        command(5, 0, 1, 0);
        command(6, 0, 0, 1);
        if (!status[30]) $fatal(1, "failed decode did not complete");
        metadata(14, 1);
        command(5, 0, 0, 0);
        command(6, 0, 0, 0);
        metadata(14, 0);
        // 8. Full reset clears configured status and generation back to 0.
        @(negedge clk);
        rst = 1;
        tick();
        @(negedge clk);
        ctrl = 0;
        rst = 0;
        metadata(7, 0);
        metadata(8, 0);
        $display("PASS qec bridge mailbox rejection/recovery metadata decode abort reset");
        $finish;
    end
    initial begin
        #10000000;
        $fatal(1, "timeout");
    end
endmodule
