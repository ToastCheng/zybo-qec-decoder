`timescale 1ns / 1ps
// Exercise both cycle-count words with a long decode.
module tb_counter;
    logic clk = 0;
    always #5 clk = !clk;
    logic rst = 1;
    logic [31:0] ctrl = 0;
    wire [31:0] status;
    integer edge_no, word_no;
    integer clock_edges = 0;
    integer accepted_edge = 0;
    integer measured_cycles = 0;
    bit result_seen = 0;
    ps_bridge dut (.*);
    // Measure input and result edges after nonblocking assignments settle.
    always @(posedge clk) begin
        clock_edges = clock_edges + 1;
        if (!rst && dut.core.in_valid && dut.core.in_ready) begin
            accepted_edge = clock_edges;
            result_seen = 0;
        end
        #1;
        if (dut.core.out_valid && !result_seen) begin
            measured_cycles = clock_edges - accepted_edge;
            result_seen = 1;
            if (dut.core.cycles !== 32'(measured_cycles)) begin
                $fatal(1, "counter differs from independent acceptance/result edges");
            end
        end
    end
    task tick;
        @(posedge clk);
        #1;
    endtask
    task command(input integer op, input integer index, input integer data);
        integer elapsed;
        @(negedge clk);
        ctrl = {~ctrl[31], 3'b0, 4'(op), 8'(index), 16'(data)};
        tick();
        elapsed = 0;
        while (status[31] != ctrl[31]) begin
            tick();
            elapsed = elapsed + 1;
            if (elapsed > 1000000) $fatal(1, "counter mailbox timeout");
        end
        if (status[29]) $fatal(1, "counter mailbox error op=%0d", op);
        if (op == 6 && elapsed < 65536) $fatal(1, "decode acknowledged too soon");
    endtask
    task metadata(input integer index, input integer expected);
        command(7, index, 0);
        if (status[15:0] !== 16'(expected)) $fatal(1, "counter metadata index=%0d got=%0d expected=%0d", index, status[15:0], expected);
    endtask
    initial begin
        repeat (2) tick();
        @(negedge clk);
        rst = 0;
        command(1, 0, 128);
        command(1, 1, 128);
        command(1, 2, 32);
        command(2, 0, 0);
        // Reverse edge order makes the odd cluster cross one half-edge per sweep.
        for (edge_no = 0; edge_no < 128; edge_no = edge_no + 1) begin
            command(1, 3, edge_no);
            command(1, 4, 127 - edge_no);
            command(1, 5, 128 - edge_no);
            command(1, 6, edge_no == 0 ? 5 : 0);
            command(1, 7, edge_no == 0 ? 16'h8000 : 0);
            command(3, 0, 0);
        end
        command(4, 0, 0);
        for (word_no = 0; word_no < 8; word_no = word_no + 1) begin
            command(5, word_no, word_no == 0 ? 1 : 0);
        end
        command(6, 0, 0);
        if (!status[30]) $fatal(1, "counter missing completion");
        metadata(10, 5);
        metadata(11, 16'h8000);
        if (!result_seen || measured_cycles <= 65535) $fatal(1, "missing long decode");
        metadata(12, measured_cycles & 65535);
        metadata(13, measured_cycles >> 16);
        metadata(14, 0);
        metadata(8, 1);
        $display("PASS qec counter mailbox cycles=%0d low16=%0d high16=%0d",
            measured_cycles, measured_cycles & 65535, measured_cycles >> 16);
        $finish;
    end
    initial begin
        #100000000;
        $fatal(1, "counter test timeout");
    end
endmodule
