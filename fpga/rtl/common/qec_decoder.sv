`timescale 1ns / 1ps
// Grow clusters in edge order, then peel the resulting forest.
module qec_decoder #(
    parameter integer MAX_DETECTORS = 128,
    parameter integer MAX_EDGES = 512,
    parameter integer MAX_OBSERVABLES = 32
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
    output logic [15:0] detector_count,
    output logic [15:0] edge_count,
    output logic [15:0] observable_count,
    input logic in_valid,
    output logic in_ready,
    input logic [MAX_DETECTORS-1:0] syndrome,
    output logic out_valid,
    input logic out_ready,
    output logic [MAX_OBSERVABLES-1:0] prediction,
    output logic decode_error,
    output logic [31:0] cycles
);
    localparam integer VB = $clog2(MAX_DETECTORS + 1) > 0 ? $clog2(MAX_DETECTORS + 1) : 1;
    typedef enum logic [4:0] {
        IDLE, INIT, CHECK, GROW, GROW_ROOTS, GROW_VALUES, GROW_SELECT,
        GROW_APPLY, RELABEL, ADVANCE, LEAVES, FIND, FIND_VALUES,
        FIND_OTHER, FIND_APPLY, VERIFY, HOLD
    } state_t;
    state_t state;
    // Endpoints 0..detector_count-1 are detectors; detector_count is the boundary.
    // Edge order fixes growth ties, and each mask labels logical observables.
    logic [15:0] graph_a [0:MAX_EDGES-1];
    logic [15:0] graph_b [0:MAX_EDGES-1];
    logic [31:0] graph_mask [0:MAX_EDGES-1];
    logic [VB-1:0] label [0:MAX_DETECTORS];
    logic parity [0:MAX_DETECTORS];
    logic work [0:MAX_DETECTORS];
    // Forest degree counts vertices, so edge capacity does not set its width.
    logic [VB:0] degree [0:MAX_DETECTORS];
    logic [1:0] growth [0:MAX_EDGES-1];
    logic forest [0:MAX_EDGES-1];
    logic [MAX_DETECTORS-1:0] input_shot;
    logic loading, load_failed;
    logic [16:0] written;
    integer unsigned cursor, edge_cursor, sweeps, leaf;
    logic pending;
    logic [VB-1:0] winner, loser;
    wire cfg_request = cfg_begin || cfg_write || cfg_commit;
    // Registers separate graph, label and parity reads at 100 MHz.
    logic [VB-1:0] a, b, ra, rb;
    logic parity_a, parity_b;
    logic [VB:0] degree_a, degree_b;
    logic [1:0] edge_growth;
    logic edge_forest;
    logic [31:0] edge_mask;
    logic leaf_work, other_work;
    logic [VB-1:0] other;
    logic [2:0] expanded;
    logic merge_parity;
    logic roots_differ;
    wire [1:0] active = {1'b0, (ra != detector_count && parity_a)}
        + {1'b0, (rb != detector_count && parity_b)};
    // The boundary wins a merge; otherwise the smaller root wins.
    wire [VB-1:0] win = (ra == detector_count || rb == detector_count)
        ? VB'(detector_count) : ((ra < rb) ? ra : rb);
    wire [VB-1:0] lose = (win == ra) ? rb : ra;

    assign in_ready = !rst && !shot_abort && !cfg_request && configured && state == IDLE;
    // HOLD keeps prediction, error and cycles stable until the result is accepted.
    assign out_valid = !rst && !shot_abort && state == HOLD;

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            configured <= 0;
            detector_count <= 0;
            edge_count <= 0;
            observable_count <= 0;
            loading <= 0;
            load_failed <= 0;
            written <= 0;
            cfg_ack <= 0;
            cfg_error <= 0;
            prediction <= 0;
            decode_error <= 0;
            cycles <= 0;
            input_shot <= 0;
            cursor <= 0;
            edge_cursor <= 0;
            sweeps <= 0;
            leaf <= 0;
            pending <= 0;
            winner <= 0;
            loser <= 0;
        end else begin
            cfg_ack <= cfg_request;
            cfg_error <= 0;
            // Rejected configuration leaves the current shot and held result intact.
            if (cfg_request) begin
                if (state != IDLE || shot_abort
                    || (cfg_begin && cfg_write) || (cfg_begin && cfg_commit)
                    || (cfg_write && cfg_commit)) begin
                    cfg_error <= 1;
                    if (state == IDLE && loading) begin
                        load_failed <= 1;
                    end
                end else if (cfg_begin) begin
                    configured <= 0;
                    loading <= 1;
                    written <= 0;
                    detector_count <= cfg_detector_count;
                    edge_count <= cfg_edge_count;
                    observable_count <= cfg_observable_count;
                    load_failed <= cfg_detector_count > MAX_DETECTORS
                        || cfg_edge_count > MAX_EDGES || cfg_observable_count > MAX_OBSERVABLES
                        || cfg_observable_count > 32;
                    cfg_error <= cfg_detector_count > MAX_DETECTORS
                        || cfg_edge_count > MAX_EDGES || cfg_observable_count > MAX_OBSERVABLES
                        || cfg_observable_count > 32;
                end else if (cfg_write) begin
                    if (!loading || load_failed || written >= edge_count
                        || cfg_edge_index != written || cfg_endpoint_a > detector_count
                        || cfg_endpoint_b > detector_count || cfg_endpoint_a == cfg_endpoint_b
                        || (cfg_observable_mask >> observable_count) != 0) begin
                        cfg_error <= 1;
                        // A bad load needs a new begin; rejected writes cannot alter a committed graph.
                        if (loading)
                            load_failed <= 1;
                    end else begin
                        graph_a[cfg_edge_index] <= cfg_endpoint_a;
                        graph_b[cfg_edge_index] <= cfg_endpoint_b;
                        graph_mask[cfg_edge_index] <= cfg_observable_mask;
                        written <= written + 1;
                    end
                end else begin
                    if (!loading || load_failed || written != edge_count) begin
                        cfg_error <= 1;
                        if (loading)
                            load_failed <= 1;
                    end else begin
                        configured <= 1;
                        loading <= 0;
                    end
                end
            end
            if (shot_abort) begin
                state <= IDLE;
                prediction <= 0;
                decode_error <= 0;
                cycles <= 0;
            end else begin
                // Count acceptance-to-result clocks, excluding HOLD; INIT rewrites work arrays.
                if (state != IDLE && state != HOLD)
                    cycles <= cycles + 1;
                case (state)
                    IDLE: begin
                        if (in_valid && in_ready) begin
                            input_shot <= syndrome;
                            prediction <= 0;
                            decode_error <= 0;
                            cycles <= 0;
                            cursor <= 0;
                            edge_cursor <= 0;
                            sweeps <= 0;
                            pending <= 0;
                            if ((syndrome >> detector_count) != 0) begin
                                decode_error <= 1;
                                state <= HOLD;
                            end else begin
                                state <= INIT;
                            end
                        end
                    end
                    INIT: begin
                        // IDLE already checked the configured detector width. Zero
                        // needs no forest: keep one counted clock and do not consult
                        // stale work arrays. The next nonzero shot rewrites them all.
                        if (input_shot == 0) begin
                            state <= HOLD;
                        end else begin
                            if (cursor <= detector_count) begin
                                label[cursor] <= VB'(cursor);
                                parity[cursor] <= cursor < detector_count ? input_shot[cursor] : 1'b0;
                                work[cursor] <= cursor < detector_count ? input_shot[cursor] : 1'b0;
                                degree[cursor] <= 0;
                            end
                            if (cursor < edge_count) begin
                                growth[cursor] <= 0;
                                forest[cursor] <= 0;
                            end
                            if (cursor >= detector_count && cursor + 1 >= edge_count) begin
                                cursor <= 0;
                                state <= CHECK;
                            end else begin
                                cursor <= cursor + 1;
                            end
                        end
                    end
                    CHECK: begin
                        if (cursor < detector_count) begin
                            pending <= pending || parity[cursor];
                            cursor <= cursor + 1;
                        end else begin
                            cursor <= 0;
                            pending <= 0;
                            if (!pending) begin
                                state <= LEAVES;
                            end else if (sweeps >= 2 * (detector_count + 1) || edge_count == 0) begin
                                decode_error <= 1;
                                state <= HOLD;
                            end else begin
                                sweeps <= sweeps + 1;
                                edge_cursor <= 0;
                                state <= GROW;
                            end
                        end
                    end
                    GROW: begin
                        a <= VB'(graph_a[edge_cursor]);
                        b <= VB'(graph_b[edge_cursor]);
                        edge_growth <= growth[edge_cursor];
                        state <= GROW_ROOTS;
                    end
                    GROW_ROOTS: begin
                        ra <= label[a];
                        rb <= label[b];
                        degree_a <= degree[a];
                        degree_b <= degree[b];
                        state <= GROW_VALUES;
                    end
                    GROW_VALUES: begin
                        parity_a <= parity[ra];
                        parity_b <= parity[rb];
                        state <= GROW_SELECT;
                    end
                    GROW_SELECT: begin
                        winner <= win;
                        loser <= lose;
                        expanded <= {1'b0, edge_growth} + {1'b0, active};
                        merge_parity <= parity_a ^ parity_b;
                        roots_differ <= ra != rb && active != 0;
                        state <= GROW_APPLY;
                    end
                    GROW_APPLY: begin
                        if (roots_differ) begin
                            growth[edge_cursor] <= expanded >= 2 ? 2 : expanded[1:0];
                            if (expanded >= 2) begin
                                parity[winner] <= merge_parity;
                                parity[loser] <= 0;
                                forest[edge_cursor] <= 1;
                                degree[a] <= degree_a + 1;
                                degree[b] <= degree_b + 1;
                                cursor <= 0;
                                state <= RELABEL;
                            end else begin
                                state <= ADVANCE;
                            end
                        end else begin
                            state <= ADVANCE;
                        end
                    end
                    RELABEL: begin
                        // Finish this merge before reading the next edge's roots.
                        if (label[cursor] == loser)
                            label[cursor] <= winner;
                        if (cursor == detector_count) begin
                            state <= ADVANCE;
                        end else begin
                            cursor <= cursor + 1;
                        end
                    end
                    ADVANCE: begin
                        if (edge_cursor + 1 >= edge_count) begin
                            cursor <= 0;
                            pending <= 0;
                            state <= CHECK;
                        end else begin
                            edge_cursor <= edge_cursor + 1;
                            state <= GROW;
                        end
                    end
                    LEAVES: begin
                        if (cursor == detector_count) begin
                            cursor <= 0;
                            state <= VERIFY;
                        end else if (degree[cursor] == 1) begin
                            leaf <= cursor;
                            edge_cursor <= 0;
                            state <= FIND;
                        end else begin
                            cursor <= cursor + 1;
                        end
                    end
                    FIND: begin
                        // A removed/nonforest edge cannot be the leaf's edge. Skip it
                        // before the registered endpoint/work pipeline, preserving the
                        // first remaining incident edge and all growth/peeling ties.
                        if (!forest[edge_cursor]) begin
                            if (edge_cursor + 1 >= edge_count) begin
                                decode_error <= 1;
                                state <= HOLD;
                            end else begin
                                edge_cursor <= edge_cursor + 1;
                            end
                        end else begin
                            a <= VB'(graph_a[edge_cursor]);
                            b <= VB'(graph_b[edge_cursor]);
                            edge_mask <= graph_mask[edge_cursor];
                            edge_forest <= forest[edge_cursor];
                            state <= FIND_VALUES;
                        end
                    end
                    FIND_VALUES: begin
                        other <= (a == leaf) ? b : a;
                        degree_a <= degree[a];
                        degree_b <= degree[b];
                        leaf_work <= work[leaf];
                        state <= FIND_OTHER;
                    end
                    FIND_OTHER: begin
                        other_work <= work[other];
                        state <= FIND_APPLY;
                    end
                    FIND_APPLY: begin
                        if (edge_forest && (a == leaf || b == leaf)) begin
                            if (leaf_work) begin
                                work[other] <= other_work ^ 1'b1;
                                prediction <= prediction ^ MAX_OBSERVABLES'(edge_mask);
                            end
                            work[leaf] <= 0;
                            forest[edge_cursor] <= 0;
                            degree[a] <= degree_a - 1;
                            degree[b] <= degree_b - 1;
                            cursor <= 0;
                            state <= LEAVES;
                        end else if (edge_cursor + 1 >= edge_count) begin
                            decode_error <= 1;
                            state <= HOLD;
                        end else begin
                            edge_cursor <= edge_cursor + 1;
                            state <= FIND;
                        end
                    end
                    VERIFY: begin
                        if (cursor == detector_count) begin
                            state <= HOLD;
                        end else if (work[cursor]) begin
                            decode_error <= 1;
                            state <= HOLD;
                        end else begin
                            cursor <= cursor + 1;
                        end
                    end
                    HOLD: begin
                        if (out_ready)
                            state <= IDLE;
                    end
                    default: begin
                        decode_error <= 1;
                        state <= HOLD;
                    end
                endcase
            end
        end
    end
endmodule
