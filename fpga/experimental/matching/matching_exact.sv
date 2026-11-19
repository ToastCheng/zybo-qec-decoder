`timescale 1ns/1ps
// Standalone exact d3/r3 Z-memory T-join solver. No CPU participation per shot.
// Graph and lossless binary64-derived integer weights are fixed by ops.svh.
module matching_exact (
    input logic clk,
    input logic rst,
    input logic in_valid,
    output logic in_ready,
    input logic [23:0] syndrome,
    output logic out_valid,
    input logic out_ready,
    output logic prediction,
    output logic [59:0] cost,
    output logic [31:0] cycles
);
    localparam integer WIDTH = 5;
    localparam integer STATES = 32;
    localparam integer OPERATIONS = 102;
    localparam logic [59:0] INF = {60{1'b1}};
    typedef enum logic [3:0] {IDLE, INIT, READ, CALC, WRITE, FINAL_READ, FINAL_LATCH, HOLD} state_t;
    state_t state;
    logic [4:0] address;
    logic [6:0] operation;
    logic bank;
    logic [23:0] shot;
    logic kind, observable;
    logic [4:0] mask, detector;
    logic [59:0] weight;
    `include "ops.svh"

    // Parity-state entries contain an exact cost and one logical-frame bit.
    // No reset clears memories: INIT overwrites all states before they are read.
    (* ram_style = "block" *) logic [60:0] bank0 [0:STATES-1];
    (* ram_style = "block" *) logic [60:0] bank1 [0:STATES-1];
    logic [60:0] read00, read01, read10, read11;
    logic [60:0] chosen;
    wire [4:0] alternate = kind
        ? (address | (shot[detector] ? mask : 5'd0))
        : (address ^ mask);
    wire [60:0] same_entry = bank ? read10 : read00;
    wire [60:0] alternate_entry = bank ? read11 : read01;
    wire [59:0] candidate_cost = alternate_entry[60:1] == INF
        ? INF : alternate_entry[60:1] + weight;
    wire memory_read = state == READ || state == FINAL_READ;
    wire write0 = state == INIT || (state == WRITE && bank);
    wire write1 = state == WRITE && !bank;
    wire [60:0] write_value = state == INIT
        ? (address == 0 ? 61'd0 : {INF, 1'b0}) : chosen;

    // Each bank has two synchronous read ports; port A also performs writes.
    // Only the opposite bank is written during a transition.
    always_ff @(posedge clk) begin
        if (write0) bank0[address] <= write_value;
        if (memory_read) begin
            read00 <= bank0[address];
            read01 <= bank0[alternate];
        end
        if (write1) bank1[address] <= chosen;
        if (memory_read) begin
            read10 <= bank1[address];
            read11 <= bank1[alternate];
        end
    end

    assign in_ready = !rst && state == IDLE;
    assign out_valid = !rst && state == HOLD;
    always_ff @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            address <= 0;
            operation <= 0;
            bank <= 0;
            shot <= 0;
            prediction <= 0;
            cost <= 0;
            cycles <= 0;
            chosen <= 0;
        end else begin
            if (state != IDLE && state != HOLD) cycles <= cycles + 1;
            case (state)
                IDLE: if (in_valid) begin
                    shot <= syndrome;
                    operation <= 0;
                    address <= 0;
                    bank <= 0;
                    cycles <= 0;
                    state <= INIT;
                end
                INIT: begin
                    if (address == STATES - 1) begin
                        address <= 0;
                        state <= READ;
                    end else address <= address + 1;
                end
                READ: state <= CALC;
                CALC: begin
                    if (kind) begin
                        // Forget a completed vertex only if its parity equals
                        // the received syndrome bit, then recycle its zero slot.
                        chosen <= (address & mask) != 0
                            ? {INF, 1'b0} : alternate_entry;
                    end else if (candidate_cost < same_entry[60:1]) begin
                        chosen <= {candidate_cost, alternate_entry[0] ^ observable};
                    end else begin
                        // A tie deterministically retains the skip-edge path.
                        chosen <= same_entry;
                    end
                    state <= WRITE;
                end
                WRITE: begin
                    if (address == STATES - 1) begin
                        address <= 0;
                        bank <= !bank;
                        if (operation == OPERATIONS - 1) state <= FINAL_READ;
                        else begin
                            operation <= operation + 1;
                            state <= READ;
                        end
                    end else begin
                        address <= address + 1;
                        state <= READ;
                    end
                end
                FINAL_READ: state <= FINAL_LATCH;
                FINAL_LATCH: begin
                    cost <= same_entry[60:1];
                    prediction <= same_entry[0];
                    state <= HOLD;
                end
                HOLD: if (out_ready) state <= IDLE;
                default: state <= IDLE;
            endcase
        end
    end
endmodule
