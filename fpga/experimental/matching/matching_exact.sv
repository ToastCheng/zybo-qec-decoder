`timescale 1ns/1ps
// Fixed-graph exact minimum-weight T-join (matching) core for the d3/r3
// Z-memory code (24 detectors, 102 compiled DP ops, frontier width 5 -> 32
// parity states).
//
// All 32 states live in flip-flops and update in parallel through a 5-stage
// XOR butterfly, using frozen 60-bit integer weights from ops.svh (strictly
// positive; ties prefer leaving the edge out). Nonzero syndromes take 512
// cycles (1 INIT + 102 * 5 pipeline cycles + 1 FINAL_LATCH); zero takes 1.
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
    localparam integer STATES = 32;
    localparam integer OPERATIONS = 102;
    localparam logic [59:0] INF = {60{1'b1}};
    typedef enum logic [3:0] {
        IDLE, ZERO_RESULT, INIT, PERMUTE, ADD_LOW, ADD_HIGH,
        COMPARE, WRITE, FINAL_LATCH, HOLD
    } state_t;
    state_t state;
    logic [6:0] operation;
    logic [23:0] shot;
    logic kind, observable;
    logic [4:0] mask, detector;
    logic [59:0] weight;
    `include "ops.svh"

    // All 32 frontier entries ({cost[59:0], observable_parity}) sit in FFs so
    // every state updates in parallel with no RAM port limits.
    //
    // A 5-stage 2:1 mux butterfly computes entries[s ^ permutation] for all 32
    // states combinationally. For edge ops (kind=0), permutation=mask fetches
    // the toggled-parity partner. For forget ops (kind=1), only states with
    // (s & mask)==0 survive (others become INF), so XOR with (shot[det] ? mask
    // : 0) selects s|mask when the detector fired and s when it did not.
    logic [60:0] entries [0:STATES-1];
    wire [60:0] permuted [0:5][0:STATES-1];
    wire [4:0] permutation = kind ? (shot[detector] ? mask : 5'd0) : mask;
    logic [59:0] alternate_cost [0:STATES-1];
    logic alternate_observable [0:STATES-1];
    logic [30:0] low_sum [0:STATES-1];
    logic [59:0] candidate [0:STATES-1];
    logic better [0:STATES-1];

    for (genvar s = 0; s < STATES; s = s + 1) begin : lanes
        assign permuted[0][s] = entries[s];
        for (genvar bit_index = 0; bit_index < 5; bit_index = bit_index + 1) begin : switches
            assign permuted[bit_index+1][s] = permutation[bit_index]
                ? permuted[bit_index][s ^ (1 << bit_index)]
                : permuted[bit_index][s];
        end
        always_ff @(posedge clk) begin
            // INIT resets all 32 states before every nonzero decode. The 60-bit
            // cost add is split across ADD_LOW/ADD_HIGH (30 bits + carry each)
            // for timing closure; empty syndromes skip straight to ZERO_RESULT
            // because all weights in ops.svh are strictly positive.
            case (state)
                INIT: entries[s] <= s == 0 ? 61'd0 : {INF, 1'b0};
                PERMUTE: begin
                    alternate_cost[s] <= permuted[5][s][60:1];
                    alternate_observable[s] <= permuted[5][s][0];
                end
                ADD_LOW: low_sum[s] <= {1'b0, alternate_cost[s][29:0]}
                    + {1'b0, weight[29:0]};
                ADD_HIGH: candidate[s] <= {
                    (alternate_cost[s][59:30] + weight[59:30] + 30'(low_sum[s][30])),
                    low_sum[s][29:0]
                };
                COMPARE: better[s] <= alternate_cost[s] != INF
                    && candidate[s] < entries[s][60:1];
                WRITE: begin
                    if (kind)
                        entries[s] <= (s & mask) != 0 ? {INF, 1'b0}
                            : {alternate_cost[s], alternate_observable[s]};
                    else if (better[s])
                        entries[s] <= {candidate[s], alternate_observable[s] ^ observable};
                end
                default: begin end
            endcase
        end
    end

    assign in_ready = !rst && state == IDLE;
    assign out_valid = !rst && state == HOLD;
    always_ff @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            operation <= 0;
            shot <= 0;
            prediction <= 0;
            cost <= 0;
            cycles <= 0;
        end else begin
            // Count active decode cycles from acceptance through FINAL_LATCH,
            // stopping once HOLD asserts out_valid.
            if (state != IDLE && state != HOLD)
                cycles <= cycles + 1;
            case (state)
                IDLE: if (in_valid) begin
                    shot <= syndrome;
                    operation <= 0;
                    cycles <= 0;
                    state <= syndrome == 0 ? ZERO_RESULT : INIT;
                end
                ZERO_RESULT: begin
                    cost <= 0;
                    prediction <= 0;
                    state <= HOLD;
                end
                INIT: state <= PERMUTE;
                PERMUTE: state <= ADD_LOW;
                ADD_LOW: state <= ADD_HIGH;
                ADD_HIGH: state <= COMPARE;
                COMPARE: state <= WRITE;
                WRITE: begin
                    if (operation == OPERATIONS - 1)
                        state <= FINAL_LATCH;
                    else begin
                        operation <= operation + 1;
                        state <= PERMUTE;
                    end
                end
                FINAL_LATCH: begin
                    cost <= entries[0][60:1];
                    prediction <= entries[0][0];
                    state <= HOLD;
                end
                HOLD: if (out_ready)
                    state <= IDLE;
                default: state <= IDLE;
            endcase
        end
    end
endmodule
