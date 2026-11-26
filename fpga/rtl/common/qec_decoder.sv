`timescale 1ns / 1ps
// Runtime-programmable Union-Find (UF) QEC decoder.
//
// Mental model
// ------------
// 1. Graph representation (uploaded at runtime via cfg_begin/cfg_write/cfg_commit):
//    Vertices 0 .. detector_count-1 are detectors; vertex `detector_count` is a
//    single shared boundary node. Each undirected edge connects two vertices
//    (graph_a, graph_b) and carries a 32-bit observable mask telling which
//    logical observables flip when that edge is chosen in the correction.
//
// 2. Two-phase decoding per shot (one shot in flight at a time):
//    - Cluster growth (CHECK -> GROW* -> RELABEL -> ADVANCE):
//      Every lit detector begins as an odd-parity cluster of size 1. Each sweep
//      visits all edges in upload order; each active (odd-parity, non-boundary)
//      endpoint adds +1 to the edge's growth counter (0 -> 1 -> 2). When growth
//      reaches 2 between two distinct clusters, the edge joins the spanning
//      forest and the two clusters merge (boundary always wins; otherwise the
//      smaller root wins). Relabeling finishes before the next edge is read so
//      upload order deterministically breaks ties. Sweeps repeat until no odd
//      non-boundary cluster remains.
//    - Forest peeling (LEAVES -> FIND* -> VERIFY):
//      Repeatedly pick a degree-1 detector vertex (never the boundary), remove
//      its incident forest edge, and if that leaf still has odd syndrome
//      (`work[leaf] == 1`), flip the neighbor's `work` bit and XOR the edge's
//      observable mask into `prediction`. VERIFY confirms no odd detector is left.
//
// 3. Pipelining for 100 MHz timing closure on Zybo Z7-10:
//    Reading graph endpoints, indexing label[]/degree[], indexing parity[] by
//    those roots, and writing back in a single cycle creates a long dependent
//    RAM/mux chain that fails setup timing at 100 MHz. GROW (5 stages) and FIND
//    (4 stages) register each lookup step across clock cycles while keeping
//    edge processing strictly serial.
//
// 4. Fast path and reset semantics:
//    - Zero-syndrome fast path: after IDLE checks that bits above detector_count
//      are zero, INIT jumps straight to HOLD in one counted clock when
//      `input_shot == 0`, skipping array initialization (the next nonzero shot
//      overwrites every entry).
//    - `shot_abort` vs `rst`: `shot_abort` cancels only the current or held shot
//      and returns to IDLE with the committed graph intact. Full `rst` clears
//      all state including the committed graph (`configured <= 0`).
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
    // Persistent graph tables populated by the cfg_* interface.
    // Endpoints 0..detector_count-1 are detectors; detector_count is the boundary.
    // Upload order fixes growth and peeling ties; graph_mask marks flipped observables.
    logic [15:0] graph_a [0:MAX_EDGES-1];
    logic [15:0] graph_b [0:MAX_EDGES-1];
    logic [31:0] graph_mask [0:MAX_EDGES-1];

    // Per-shot Union-Find and peeling working arrays (re-initialized on each nonzero shot).
    // - label[v]:  current cluster root for vertex v (maintained flat by RELABEL)
    // - parity[r]: 1 if cluster rooted at r has odd defect parity (0 for boundary)
    // - work[v]:   remaining defect bit at vertex v during forest peeling
    // - degree[v]: incident forest-edge count; bounded by vertex count, not MAX_EDGES
    // - growth[e]: half-edge growth accumulator (0, 1, or 2 = fully grown)
    // - forest[e]: 1 while edge e belongs to the spanning forest being peeled
    logic [VB-1:0] label [0:MAX_DETECTORS];
    logic parity [0:MAX_DETECTORS];
    logic work [0:MAX_DETECTORS];
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

    // Registered stage intermediates that break dependent memory reads across
    // clock edges during GROW* and FIND* so the design closes setup at 100 MHz.
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

    // Count how many endpoints of the current edge belong to active (odd, non-boundary)
    // clusters (0, 1, or 2); this is added to edge_growth in GROW_SELECT.
    wire [1:0] active = {1'b0, (ra != detector_count && parity_a)}
        + {1'b0, (rb != detector_count && parity_b)};
    // Merge root tie-breaker: the boundary always wins; otherwise the lower root index wins.
    wire [VB-1:0] win = (ra == detector_count || rb == detector_count)
        ? VB'(detector_count) : ((ra < rb) ? ra : rb);
    wire [VB-1:0] lose = (win == ra) ? rb : ra;

    // Accept a new shot only when idle, configured, and not racing a config or abort.
    assign in_ready = !rst && !shot_abort && !cfg_request && configured && state == IDLE;
    // HOLD keeps prediction, decode_error, and cycles stable until out_ready consumes them.
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
            // Graph configuration protocol: begin -> edge_count sequential writes -> commit.
            // Rejected requests leave any active shot, held result, or committed graph untouched.
            if (cfg_request) begin
                if (state != IDLE || shot_abort
                    || (cfg_begin && cfg_write) || (cfg_begin && cfg_commit)
                    || (cfg_write && cfg_commit)) begin
                    cfg_error <= 1;
                    if (state == IDLE && loading) begin
                        load_failed <= 1;
                    end
                end else if (cfg_begin) begin
                    // Disarm decoding immediately until the new graph is committed cleanly.
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
                    // Edges must arrive in order 0..edge_count-1 with distinct valid
                    // endpoints and no observable mask bits set above observable_count.
                    if (!loading || load_failed || written >= edge_count
                        || cfg_edge_index != written || cfg_endpoint_a > detector_count
                        || cfg_endpoint_b > detector_count || cfg_endpoint_a == cfg_endpoint_b
                        || (cfg_observable_mask >> observable_count) != 0) begin
                        cfg_error <= 1;
                        // Poison the in-progress load so commit cannot succeed without a fresh begin.
                        if (loading)
                            load_failed <= 1;
                    end else begin
                        graph_a[cfg_edge_index] <= cfg_endpoint_a;
                        graph_b[cfg_edge_index] <= cfg_endpoint_b;
                        graph_mask[cfg_edge_index] <= cfg_observable_mask;
                        written <= written + 1;
                    end
                end else begin
                    // Commit succeeds only when every declared edge was written cleanly.
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
            // shot_abort cancels only the active or held shot; the committed graph stays valid.
            if (shot_abort) begin
                state <= IDLE;
                prediction <= 0;
                decode_error <= 0;
                cycles <= 0;
            end else begin
                // Count acceptance-to-result clock cycles (excludes IDLE and HOLD).
                if (state != IDLE && state != HOLD)
                    cycles <= cycles + 1;
                case (state)
                    // Wait for a shot, latch the syndrome, and reject set bits past detector_count.
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
                    // Initialize per-vertex and per-edge working arrays for a nonzero shot.
                    // Zero-syndrome fast path: jump straight to HOLD (1 counted cycle) without
                    // clearing working arrays, since this shot never reads them and the next
                    // nonzero shot rewrites every active entry.
                    INIT: begin
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
                    // Scan detector parities (excluding the boundary). If none are odd,
                    // cluster growth is done and peeling begins; otherwise start a new sweep
                    // unless the sweep bound is exceeded (disconnected odd component).
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
                    // --- Cluster growth pipeline (5 registered stages per edge) ---
                    // Stage 1: fetch the current edge's endpoints and prior growth count.
                    GROW: begin
                        a <= VB'(graph_a[edge_cursor]);
                        b <= VB'(graph_b[edge_cursor]);
                        edge_growth <= growth[edge_cursor];
                        state <= GROW_ROOTS;
                    end
                    // Stage 2: look up both endpoints' current cluster roots and forest degrees.
                    GROW_ROOTS: begin
                        ra <= label[a];
                        rb <= label[b];
                        degree_a <= degree[a];
                        degree_b <= degree[b];
                        state <= GROW_VALUES;
                    end
                    // Stage 3: look up each cluster root's odd-defect parity.
                    GROW_VALUES: begin
                        parity_a <= parity[ra];
                        parity_b <= parity[rb];
                        state <= GROW_SELECT;
                    end
                    // Stage 4: compute updated growth, merge winner/loser, and combined parity.
                    GROW_SELECT: begin
                        winner <= win;
                        loser <= lose;
                        expanded <= {1'b0, edge_growth} + {1'b0, active};
                        merge_parity <= parity_a ^ parity_b;
                        roots_differ <= ra != rb && active != 0;
                        state <= GROW_APPLY;
                    end
                    // Stage 5: write updated growth; if the edge saturated (>= 2), add it
                    // to the spanning forest, update cluster parities and degrees, and relabel.
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
                    // Flatten all vertices belonging to the losing cluster onto `winner`
                    // before reading the next edge, keeping root lookups O(1) and tie order exact.
                    RELABEL: begin
                        if (label[cursor] == loser)
                            label[cursor] <= winner;
                        if (cursor == detector_count) begin
                            state <= ADVANCE;
                        end else begin
                            cursor <= cursor + 1;
                        end
                    end
                    // Step to the next edge in the sweep, or return to CHECK after the last edge.
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
                    // --- Forest peeling ---
                    // Scan detectors 0..detector_count-1 for a degree-1 leaf (boundary is skipped).
                    // When no leaves remain, move to VERIFY.
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
                    // --- Leaf-edge search & peel pipeline (4 registered stages) ---
                    // Stage 1: skip non-forest edges in 1 cycle without entering the lookup
                    // pipeline; for a forest edge, fetch its endpoints and observable mask.
                    FIND: begin
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
                    // Stage 2: identify the opposite endpoint and fetch degrees plus leaf defect bit.
                    FIND_VALUES: begin
                        other <= (a == leaf) ? b : a;
                        degree_a <= degree[a];
                        degree_b <= degree[b];
                        leaf_work <= work[leaf];
                        state <= FIND_OTHER;
                    end
                    // Stage 3: fetch the opposite endpoint's current defect bit.
                    FIND_OTHER: begin
                        other_work <= work[other];
                        state <= FIND_APPLY;
                    end
                    // Stage 4: if this forest edge touches `leaf`, peel it (propagate any odd
                    // defect to `other`, XOR observable mask into prediction, decrement degrees)
                    // and restart leaf scan from vertex 0; otherwise inspect the next edge.
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
                    // Confirm every detector's defect bit was canceled during peeling;
                    // any remaining 1 indicates a cycle or unresolvable syndrome.
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
                    // Hold prediction, decode_error, and cycles stable until out_ready accepts them.
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
