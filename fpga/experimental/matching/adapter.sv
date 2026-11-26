`timescale 1ns/1ps
// Configuration and shot-interface wrapper around the fixed d3/r3 Z-memory
// exact matching core (24 detectors, 78 edges, 1 observable).
//
// Edge weights are frozen in ops.svh at synthesis time, so this adapter acts
// as an identity gate: decoding stays disarmed (configured=0) until the host
// uploads all 78 edges matching graph_identity.svh in exact order.
module qec_decoder #(
    parameter integer MAX_DETECTORS = 24,
    parameter integer MAX_EDGES = 78,
    parameter integer MAX_OBSERVABLES = 1
) (
    input logic clk,
    input logic rst,
    input logic shot_abort,
    input logic cfg_begin,
    input logic cfg_write,
    input logic cfg_commit,
    input logic [15:0] cfg_detector_count,
    input logic [15:0] cfg_edge_count,
    input logic [15:0] cfg_observable_count,
    input logic [15:0] cfg_edge_index,
    input logic [15:0] cfg_endpoint_a,
    input logic [15:0] cfg_endpoint_b,
    input logic [31:0] cfg_observable_mask,
    output logic cfg_ack,
    output logic cfg_error,
    output logic configured,
    output wire [15:0] detector_count,
    output wire [15:0] edge_count,
    output wire [15:0] observable_count,
    input logic in_valid,
    output wire in_ready,
    input logic [MAX_DETECTORS-1:0] syndrome,
    output wire out_valid,
    input logic out_ready,
    output wire [MAX_OBSERVABLES-1:0] prediction,
    output wire decode_error,
    output wire [31:0] cycles
);
    logic loading, poisoned;
    logic [15:0] written;
    logic [63:0] expected_edge;
    logic busy;
    logic exact_ready, exact_valid, exact_prediction;
    wire request = cfg_begin || cfg_write || cfg_commit;
    wire accept = in_valid && in_ready;
    wire [59:0] exact_cost;
    wire [31:0] exact_cycles;
    logic [31:0] measured_cycles;
    `include "graph_identity.svh"
    assign detector_count = configured ? 16'd24 : 16'd0;
    assign edge_count = configured ? 16'd78 : 16'd0;
    assign observable_count = configured ? 16'd1 : 16'd0;
    assign in_ready = configured && exact_ready && !request && !shot_abort && !rst;
    assign out_valid = exact_valid && !shot_abort;
    assign prediction = {{(MAX_OBSERVABLES-1){1'b0}}, exact_prediction};
    // Cross-check the core's cycle counter against an independent counter that
    // runs from shot acceptance to out_valid (excluding output hold cycles).
    assign cycles = exact_cycles;
    assign decode_error = exact_valid && (measured_cycles != exact_cycles);
    matching_exact exact (
        .clk(clk), .rst(rst || shot_abort),
        .in_valid(accept), .in_ready(exact_ready), .syndrome(syndrome[23:0]),
        .out_valid(exact_valid), .out_ready(out_ready),
        .prediction(exact_prediction), .cost(exact_cost), .cycles(exact_cycles)
    );
    always_ff @(posedge clk) begin
        if (rst || shot_abort) begin
            busy <= 0;
            measured_cycles <= 0;
        end else if (accept) begin
            busy <= 1;
            measured_cycles <= 0;
        end else if (busy && !exact_valid) begin
            measured_cycles <= measured_cycles + 1;
        end else if (exact_valid) begin
            busy <= 0;
        end
    end
    // Graph-identity gate: verify dimensions (24/78/1) and every uploaded edge
    // against graph_identity.svh. Any mismatch sets poisoned and fails commit.
    always_ff @(posedge clk) begin
        if (rst) begin
            loading <= 0;
            poisoned <= 0;
            written <= 0;
            configured <= 0;
            cfg_ack <= 0;
            cfg_error <= 0;
        end else begin
            cfg_ack <= request;
            cfg_error <= 0;
            if (request) begin
                if (!exact_ready || shot_abort ||
                    (cfg_begin && cfg_write) || (cfg_begin && cfg_commit) ||
                    (cfg_write && cfg_commit)) begin
                    cfg_error <= 1;
                    if (loading) poisoned <= 1;
                end else if (cfg_begin) begin
                    configured <= 0;
                    written <= 0;
                    loading <= 1;
                    poisoned <= cfg_detector_count != 24 || cfg_edge_count != 78 || cfg_observable_count != 1;
                    cfg_error <= cfg_detector_count != 24 || cfg_edge_count != 78 || cfg_observable_count != 1;
                end else if (cfg_write) begin
                    if (loading && cfg_edge_index == written && written < 78)
                        written <= written + 1;
                    if (!loading || cfg_edge_index != written || written >= 78 ||
                        {cfg_endpoint_a, cfg_endpoint_b, cfg_observable_mask} != expected_edge) begin
                        poisoned <= 1;
                        cfg_error <= 1;
                    end else begin
                        written <= written + 1;
                    end
                end else if (cfg_commit) begin
                    loading <= 0;
                    configured <= loading && !poisoned && written == 78;
                    cfg_error <= !loading || poisoned || written != 78;
                end
            end
        end
    end
endmodule
