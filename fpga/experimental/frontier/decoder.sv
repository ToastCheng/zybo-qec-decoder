`timescale 1ns/1ps
// Programmable parity-frontier DP exact matching (minimum-weight T-join) core.
//
// Instead of graph edges for Union-Find, the host uploads a compiled DP
// program of edge and forget operations over a parity frontier of up to
// MAX_WIDTH bits (up to 4,096 states). Each state stores a 64-bit integer cost
// and a 1-bit logical observable parity across four parallel BRAM lanes.
// The uploaded 10-byte program records are checksummed in hardware (IEEE CRC-32)
// and exposed on program_crc.
module qec_decoder #(
    parameter integer MAX_DETECTORS = 128,
    parameter integer MAX_EDGES = 1024,
    parameter integer MAX_OBSERVABLES = 1,
    parameter integer MAX_WIDTH = 12
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
    output wire in_ready,
    input logic [MAX_DETECTORS-1:0] syndrome,
    output wire out_valid,
    input logic out_ready,
    output wire [MAX_OBSERVABLES-1:0] prediction,
    output wire decode_error,
    output logic [31:0] cycles,
    output wire [31:0] program_crc
);
    localparam integer GROUP_BITS = MAX_WIDTH - 2;
    localparam integer GROUPS = 1 << GROUP_BITS;
    localparam integer OPS = MAX_EDGES / 2;
    localparam logic [63:0] INF = 64'hffffffffffffffff;
    typedef enum logic [3:0] {
        IDLE, ZERO_RESULT, INIT, PROGRAM_READ, PROGRAM_PREP, READ, SELECT_OTHER,
        ADD_LOW, ADD_HIGH, COMPARE, WRITE, FINAL_READ, FINAL_LATCH, HOLD
    } state_t;
    state_t state;
    logic [GROUP_BITS-1:0] group_index;
    logic [GROUP_BITS:0] groups_used;
    logic bank;
    logic [8:0] operation;
    logic [15:0] operation_count;
    logic [MAX_DETECTORS-1:0] shot;
    logic op_kind, op_observable;
    logic [MAX_WIDTH-1:0] op_mask;
    logic [6:0] op_detector;
    logic [63:0] op_weight;
    logic program_kind [0:OPS-1];
    logic program_observable [0:OPS-1];
    logic [MAX_WIDTH-1:0] program_mask [0:OPS-1];
    logic [6:0] program_detector [0:OPS-1];
    logic [63:0] program_weight [0:OPS-1];
    logic [63:0] result_cost;
    logic result_prediction;
    logic loading, poisoned, crc_active;
    logic [15:0] written, declared_records;
    logic [4:0] frontier_width;
    logic [15:0] first_a, first_b;
    logic [31:0] first_weight;
    logic [31:0] crc;
    logic [79:0] crc_record;
    logic [3:0] crc_byte;
    logic write_failed;
    logic counter_busy;
    logic [31:0] independent_cycles;
    wire request = cfg_begin || cfg_write || cfg_commit;
    wire accept = in_valid && in_ready;
    logic [MAX_WIDTH-1:0] permutation;
    wire [GROUP_BITS-1:0] alternate_group = group_index ^ permutation[MAX_WIDTH-1:2];
    wire [64:0] direct0 [0:3];
    wire [64:0] direct1 [0:3];
    wire [64:0] alternate0 [0:3];
    wire [64:0] alternate1 [0:3];
    wire [64:0] selected [0:3];
    logic [32:0] low_sum [0:3];
    logic [63:0] candidate [0:3];
    logic finite [0:3];
    logic better [0:3];
    assign in_ready = !rst && !shot_abort && !request && configured && state == IDLE;
    assign out_valid = !rst && !shot_abort && state == HOLD;
    assign prediction = MAX_OBSERVABLES'(result_prediction);
    assign decode_error = out_valid && (result_cost == INF || cycles != independent_cycles);
    assign program_crc = ~crc;

    // Fold one byte into a running reflected IEEE CRC-32 state.
    // program_crc applies the final bitwise inversion.
    function automatic [31:0] crc8(input logic [31:0] previous, input logic [7:0] value);
        logic [31:0] x;
        begin
            x = previous ^ {24'b0, value};
            for (integer bit_index = 0; bit_index < 8; bit_index = bit_index + 1)
                x = (x >> 1) ^ (x[0] ? 32'hedb88320 : 32'd0);
            crc8 = x;
        end
    endfunction

    // Four parallel BRAM lanes (low 2 bits of the frontier parity state) with
    // ping-pong banks (memory0/memory1) indexed by group_index (upper bits).
    // Each entry packs {cost[63:0], observable_parity}.
    //
    // A transition pairs state s with s ^ permutation. Because XOR on the
    // 2-bit lane index is a bijection on {0..3}, reading group_index and
    // alternate_group in all four lanes fetches both same_entry and other_entry
    // simultaneously with no BRAM bank conflicts.
    for (genvar lane = 0; lane < 4; lane = lane + 1) begin : lanes
        (* ram_style = "block" *) logic [64:0] memory0 [0:GROUPS-1];
        (* ram_style = "block" *) logic [64:0] memory1 [0:GROUPS-1];
        logic [64:0] read0a, read0b, read1a, read1b, same_entry, other_entry;
        wire invalid_projection = (((MAX_WIDTH'(group_index) << 2) | MAX_WIDTH'(lane)) & op_mask) != 0;
        assign direct0[lane] = read0a;
        assign direct1[lane] = read1a;
        assign alternate0[lane] = read0b;
        assign alternate1[lane] = read1b;
        // op_kind=1 (forget detector): keep states with (s & op_mask) == 0 and
        // copy other_entry; mark projected-out states unreachable (INF).
        // op_kind=0 (edge): take candidate if strictly cheaper, flipping obs.
        assign selected[lane] = op_kind
            ? (invalid_projection ? {INF, 1'b0} : other_entry)
            : (better[lane] ? {candidate[lane], other_entry[0] ^ op_observable} : same_entry);
        always_ff @(posedge clk) begin
            if (state == INIT)
                memory0[group_index] <= group_index == 0 && lane == 0 ? 65'd0 : {INF, 1'b0};
            else if (state == WRITE && bank)
                memory0[group_index] <= selected[lane];
            if (state == WRITE && !bank)
                memory1[group_index] <= selected[lane];
            if (state == READ || state == FINAL_READ) begin
                read0a <= memory0[group_index];
                read0b <= memory0[alternate_group];
                read1a <= memory1[group_index];
                read1b <= memory1[alternate_group];
            end
            if (state == SELECT_OTHER) begin
                same_entry <= bank ? read1a : read0a;
                other_entry <= bank ? alternate1[lane ^ permutation[1:0]]
                    : alternate0[lane ^ permutation[1:0]];
            end
            // Split the 64-bit cost addition across ADD_LOW and ADD_HIGH
            // (32 bits + carry per cycle) to close timing at 100 MHz.
            if (state == ADD_LOW) begin
                low_sum[lane] <= {1'b0, other_entry[32:1]} + {1'b0, op_weight[31:0]};
                finite[lane] <= other_entry[64:1] != INF;
            end
            if (state == ADD_HIGH)
                candidate[lane] <= {other_entry[64:33] + op_weight[63:32] + 32'(low_sum[lane][32]), low_sum[lane][31:0]};
            if (state == COMPARE)
                better[lane] <= finite[lane] && candidate[lane] < same_entry[64:1];
        end
    end

    // Independent cycle counter cross-checked against the FSM's cycles counter
    // in decode_error to catch any datapath timing/bookkeeping mismatch in PL.
    always_ff @(posedge clk) begin
        if (rst || shot_abort) begin
            counter_busy <= 0;
            independent_cycles <= 0;
        end else if (accept) begin
            counter_busy <= 1;
            independent_cycles <= 0;
        end else if (counter_busy && !out_valid)
            independent_cycles <= independent_cycles + 1;
        else if (out_valid)
            counter_busy <= 0;
    end

    // Main decode FSM: handles the 1-cycle zero-syndrome shortcut, table
    // initialization, per-operation 6-cycle group sweeps across ping-pong
    // banks, final state-0 readback, and output hold until out_ready.
    always_ff @(posedge clk) begin
        if (rst || shot_abort) begin
            state <= IDLE;
            cycles <= 0;
            group_index <= 0;
            operation <= 0;
            shot <= 0;
            bank <= 0;
            result_cost <= 0;
            result_prediction <= 0;
            op_kind <= 0;
            op_observable <= 0;
            op_mask <= 0;
            op_detector <= 0;
            op_weight <= 0;
            permutation <= 0;
        end else begin
            if (state != IDLE && state != HOLD)
                cycles <= cycles + 1;
            case (state)
                IDLE: if (accept) begin
                    shot <= syndrome;
                    cycles <= 0;
                    group_index <= 0;
                    operation <= 0;
                    bank <= 0;
                    state <= syndrome == 0 ? ZERO_RESULT : INIT;
                end
                ZERO_RESULT: begin
                    result_cost <= 0;
                    result_prediction <= 0;
                    state <= HOLD;
                end
                INIT: begin
                    if ({1'b0, group_index} == groups_used - 1) begin
                        group_index <= 0;
                        state <= PROGRAM_READ;
                    end else
                        group_index <= group_index + 1;
                end
                PROGRAM_READ: begin
                    op_kind <= program_kind[operation];
                    op_observable <= program_observable[operation];
                    op_mask <= program_mask[operation];
                    op_detector <= program_detector[operation];
                    op_weight <= program_weight[operation];
                    state <= PROGRAM_PREP;
                end
                PROGRAM_PREP: begin
                    permutation <= op_kind ? (shot[op_detector] ? op_mask : {MAX_WIDTH{1'b0}}) : op_mask;
                    state <= READ;
                end
                READ: state <= SELECT_OTHER;
                SELECT_OTHER: state <= ADD_LOW;
                ADD_LOW: state <= ADD_HIGH;
                ADD_HIGH: state <= COMPARE;
                COMPARE: state <= WRITE;
                WRITE: begin
                    if ({1'b0, group_index} == groups_used - 1) begin
                        group_index <= 0;
                        bank <= !bank;
                        if ({7'b0, operation} == operation_count - 1)
                            state <= FINAL_READ;
                        else begin
                            operation <= operation + 1;
                            state <= PROGRAM_READ;
                        end
                    end else begin
                        group_index <= group_index + 1;
                        state <= READ;
                    end
                end
                FINAL_READ: state <= FINAL_LATCH;
                FINAL_LATCH: begin
                    result_cost <= bank ? direct1[0][64:1] : direct0[0][64:1];
                    result_prediction <= bank ? direct1[0][0] : direct0[0][0];
                    state <= HOLD;
                end
                HOLD: if (out_ready)
                    state <= IDLE;
                default: state <= IDLE;
            endcase
        end
    end

    // Program loader and hardware CRC-32.
    // Each DP operation arrives as two consecutive 10-byte cfg_write records:
    //   - even record: header (endpoint_a = {op_kind, 3'b0, mask},
    //                  endpoint_b = {op_observable, 8'b0, detector}) + weight[31:0]
    //   - odd record:  identical header + weight[63:32], committing the op
    // Every accepted record is shifted byte-by-byte through crc8 (10 cycles)
    // in little-endian wire order {weight_word, endpoint_b, endpoint_a, index}
    // before asserting cfg_ack. Any bad record poisons the load until cfg_begin.
    always_ff @(posedge clk) begin
        if (rst) begin
            configured <= 0;
            detector_count <= 0;
            edge_count <= 0;
            observable_count <= 0;
            operation_count <= 0;
            groups_used <= 0;
            loading <= 0;
            poisoned <= 0;
            crc_active <= 0;
            crc <= 32'hffffffff;
            crc_byte <= 0;
            crc_record <= 0;
            written <= 0;
            declared_records <= 0;
            frontier_width <= 2;
            first_a <= 0;
            first_b <= 0;
            first_weight <= 0;
            cfg_ack <= 0;
            cfg_error <= 0;
            write_failed <= 0;
        end else begin
            cfg_ack <= 0;
            cfg_error <= 0;
            if (crc_active) begin
                crc <= crc8(crc, crc_record[7:0]);
                crc_record <= crc_record >> 8;
                crc_byte <= crc_byte + 1;
                if (crc_byte == 9) begin
                    crc_active <= 0;
                    written <= written + 1;
                    cfg_ack <= 1;
                    cfg_error <= write_failed;
                end
            end else if (request) begin
                cfg_ack <= 1;
                if (state != IDLE || shot_abort ||
                    (cfg_begin && cfg_write) || (cfg_begin && cfg_commit) || (cfg_write && cfg_commit)) begin
                    cfg_error <= 1;
                    if (loading) poisoned <= 1;
                end else if (cfg_begin) begin
                    configured <= 0;
                    detector_count <= 0;
                    edge_count <= 0;
                    observable_count <= 0;
                    loading <= 1;
                    written <= 0;
                    frontier_width <= 2;
                    declared_records <= cfg_edge_count;
                    operation_count <= cfg_edge_count >> 1;
                    crc <= 32'hffffffff;
                    poisoned <= cfg_detector_count == 0 || cfg_detector_count > MAX_DETECTORS ||
                        cfg_edge_count < 2 || cfg_edge_count > MAX_EDGES || cfg_edge_count[0] || cfg_observable_count != 1;
                    cfg_error <= cfg_detector_count == 0 || cfg_detector_count > MAX_DETECTORS ||
                        cfg_edge_count < 2 || cfg_edge_count > MAX_EDGES || cfg_edge_count[0] || cfg_observable_count != 1;
                    if (cfg_detector_count != 0 && cfg_detector_count <= MAX_DETECTORS)
                        detector_count <= cfg_detector_count;
                end else if (cfg_write) begin
                    if (!loading || cfg_edge_index != written || written >= declared_records ||
                        (cfg_endpoint_a & (16'h7fff ^ ((16'd1 << MAX_WIDTH) - 1))) != 0 ||
                        cfg_endpoint_a[MAX_WIDTH-1:0] == 0 ||
                        (cfg_endpoint_b & 16'h7f80) != 0 || cfg_endpoint_b[6:0] >= detector_count ||
                        (cfg_edge_index[0] && (cfg_endpoint_a != first_a || cfg_endpoint_b != first_b))) begin
                        poisoned <= 1;
                        cfg_error <= 1;
                    end else begin
                        cfg_ack <= 0;
                        crc_active <= 1;
                        crc_byte <= 0;
                        crc_record <= {cfg_observable_mask, cfg_endpoint_b, cfg_endpoint_a, cfg_edge_index};
                        write_failed <= 0;
                        if (!cfg_edge_index[0]) begin
                            first_a <= cfg_endpoint_a;
                            first_b <= cfg_endpoint_b;
                            first_weight <= cfg_observable_mask;
                            for (integer bit_index = 0; bit_index < MAX_WIDTH; bit_index = bit_index + 1)
                                if (cfg_endpoint_a[bit_index] && bit_index + 1 > frontier_width)
                                    frontier_width <= 5'(bit_index + 1);
                        end else begin
                            program_kind[cfg_edge_index[9:1]] <= cfg_endpoint_a[15];
                            program_mask[cfg_edge_index[9:1]] <= cfg_endpoint_a[MAX_WIDTH-1:0];
                            program_detector[cfg_edge_index[9:1]] <= cfg_endpoint_b[6:0];
                            program_observable[cfg_edge_index[9:1]] <= cfg_endpoint_b[15];
                            program_weight[cfg_edge_index[9:1]] <= {cfg_observable_mask, first_weight};
                        end
                    end
                end else if (cfg_commit) begin
                    loading <= 0;
                    if (!loading || poisoned || written != declared_records) begin
                        configured <= 0;
                        cfg_error <= 1;
                    end else begin
                        configured <= 1;
                        edge_count <= declared_records;
                        observable_count <= 1;
                        groups_used <= (GROUP_BITS+1)'(1 << (frontier_width - 2));
                    end
                end
            end
        end
    end
endmodule
