`timescale 1ns / 1ps
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
    task tick;
        @(posedge clk);
        #1;
    endtask
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
    task metadata(input integer idx, input integer expected);
        command(7, idx, 0, 0);
        if (status[15:0] !== 16'(expected)) $fatal(1, "metadata %0d got=%h expected=%h", idx, status[15:0], expected);
    endtask
    task stage(input integer idx, input integer data);
        command(1, idx, data, 0);
    endtask
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
        load_graph();
        metadata(8, 1);
        command(2, 1, 0, 1); // Reject unused indices rather than interpreting them as zero.
        command(3, 1, 0, 1);
        command(4, 1, 0, 1);
        command(6, 1, 0, 1);
        command(8, 1, 0, 1);
        metadata(7, 1);
        metadata(4, 1);
        metadata(5, 1);
        metadata(6, 32);
        command(6, 0, 0, 1); // Require writes to every active syndrome word.
        command(5, 1, 0, 1); // Reject words beyond the configured syndrome.
        command(5, 0, 2, 1); // Reject set bits above the detector count.
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
        command(8, 0, 0, 0);
        metadata(7, 1);
        metadata(8, 1);
        metadata(10, 0);
        command(6, 0, 0, 1);
        command(5, 0, 0, 0);
        command(6, 0, 0, 0);
        metadata(10, 0);
        // A failed load cannot expose the previous graph.
        command(2, 0, 0, 0);
        command(4, 0, 0, 1);
        metadata(7, 0);
        command(6, 0, 0, 1);
        load_graph();
        metadata(8, 2);
        command(5, 0, 1, 0);
        command(6, 0, 0, 0);
        metadata(11, 16'h8000);
        // Reload two words with a partial last word and independent observable masks.
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
        command(6, 0, 0, 1); // Require fresh words on the second shot.
        command(8, 0, 0, 0);
        metadata(7, 1);
        metadata(8, 3);
        command(5, 0, 1, 0);
        command(5, 1, 0, 0);
        command(6, 0, 0, 0);
        metadata(10, 3);
        metadata(11, 0);
        // Recover after a disconnected graph returns a decoding error.
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
