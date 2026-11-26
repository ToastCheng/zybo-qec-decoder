`timescale 1ns / 1ps
// AXI GPIO toggle-mailbox bridge between the ARM PS and qec_decoder.
//
// How the handshake works
// -----------------------
// The AXI GPIO block and qec_decoder share the same 100 MHz fabric clock, and
// only one command may be in flight at a time. To send a command, ARM writes
// OPCODE, INDEX, DATA, and flips ctrl[31] (REQ) to the opposite of status[31]
// (ACK), holding ctrl steady until status[31] flips to match ctrl[31].
//
// Status flags
// ------------
// - DONE  (status[30]): latched flag showing the last decode finished and its
//   result words (metadata 10..14) are populated. DONE means completed, not
//   succeeded: a decode error still drives DONE=1 alongside ERROR=1. DONE
//   clears on a new decode launch, a new graph load (begin), or shot abort.
// - ERROR (status[29]): describes only the current command acknowledgement
//   (bad opcode/index, rejected graph write, decode error on op 6, or invalid
//   metadata index on op 7). A later valid metadata read clears ERROR on the
//   status bus without clearing saved_error (metadata index 14).
module ps_bridge #(
    parameter integer MAX_DETECTORS = 128,
    parameter integer MAX_EDGES = 512,
    parameter integer MAX_OBSERVABLES = 32
) (
    input logic clk,
    input logic rst,
    input logic [31:0] ctrl,
    output logic [31:0] status
);
    localparam integer WORDS = (MAX_DETECTORS + 15) / 16;
    typedef enum logic [3:0] {
        IDLE, BEGIN_CONFIG, APPEND_EDGE, COMMIT_CONFIG, WAIT_CONFIG,
        LAUNCH, WAIT_RESULT, ABORT_SHOT, ABORT_ACK
    } state_t;
    state_t state;
    // GPIO mailbox word layouts (field widths are not drawn to scale).
    //
    // ctrl (ARM -> PL): hold every bit stable until status.ACK matches ctrl.REQ.
    //  31    30:28     27:24      23:16             15:0
    // +-----+---------+----------+-----------------+------------------+
    // | REQ | ignored | OPCODE   | INDEX           | DATA             |
    // +-----+---------+----------+-----------------+------------------+
    //    1       3         4              8                  16 bits
    //
    // status (PL -> ARM): DONE is latched decode completion, not logical success.
    //  31    30     29      28:16                   15:0
    // +-----+------+-------+-----------------------+------------------+
    // | ACK | DONE | ERROR | zero                  | READ_DATA        |
    // +-----+------+-------+-----------------------+------------------+
    //    1      1      1              13                     16 bits
    //
    // Opcodes (INDEX must be 0 for opcodes 2, 3, 4, 6, and 8):
    //   1 = write staging register (INDEX 0..7)
    //   2 = begin graph load using staging[0..2]
    //   3 = append edge using staging[3..7]
    //   4 = commit graph (increments `generation` on success)
    //   5 = write 16-bit syndrome word (INDEX w -> detectors 16*w .. 16*w+15)
    //   6 = launch decode (requires all active syndrome words written fresh)
    //   7 = read metadata register INDEX (0..14) into status.READ_DATA
    //   8 = abort current shot / clear cached result while keeping the graph
    // See docs/decoder-design.md for the full protocol specification.
    //
    // Staging register map (written via opcode 1):
    //   0 = detector_count, 1 = edge_count, 2 = observable_count,
    //   3 = edge_index,     4 = endpoint_a, 5 = endpoint_b,
    //   6 = mask_lo,        7 = mask_hi.
    //
    // 32-bit observable mask assembled from staging[7:6]:
    //  31                         16 15                              0
    // +-----------------------------+---------------------------------+
    // | staging[7]: mask high       | staging[6]: mask low            |
    // +-----------------------------+---------------------------------+
    //
    // Syndrome packing (opcode 5, INDEX = w): DATA[b] is detector 16*w + b
    // (b = 0..15). Any bit at or above detector_count must be 0.
    logic [15:0] staging [0:7];
    logic [WORDS*16-1:0] shot;
    logic [WORDS-1:0] written_words;
    logic request_bit;
    logic [3:0] request_opcode;
    logic [31:0] generation;
    logic [31:0] saved_prediction, saved_cycles;
    logic saved_error, result_complete;
    wire cfg_ack, cfg_error, configured;
    wire [15:0] detector_count, edge_count, observable_count;
    wire in_ready, out_valid, decode_error;
    wire [MAX_OBSERVABLES-1:0] prediction;
    wire [31:0] cycles;
    logic all_words_written;
    logic [15:0] metadata;
    logic metadata_valid;
    integer k;

    qec_decoder #(
        .MAX_DETECTORS(MAX_DETECTORS),
        .MAX_EDGES(MAX_EDGES),
        .MAX_OBSERVABLES(MAX_OBSERVABLES)
    ) core (
        .clk(clk),
        .rst(rst),
        .shot_abort(state == ABORT_SHOT),
        .cfg_begin(state == BEGIN_CONFIG),
        .cfg_write(state == APPEND_EDGE),
        .cfg_commit(state == COMMIT_CONFIG),
        .cfg_detector_count(staging[0]),
        .cfg_edge_count(staging[1]),
        .cfg_observable_count(staging[2]),
        .cfg_edge_index(staging[3]),
        .cfg_endpoint_a(staging[4]),
        .cfg_endpoint_b(staging[5]),
        .cfg_observable_mask({staging[7], staging[6]}),
        .cfg_ack(cfg_ack),
        .cfg_error(cfg_error),
        .configured(configured),
        .detector_count(detector_count),
        .edge_count(edge_count),
        .observable_count(observable_count),
        .in_valid(state == LAUNCH),
        .in_ready(in_ready),
        .syndrome(shot[MAX_DETECTORS-1:0]),
        .out_valid(out_valid),
        .out_ready(state == WAIT_RESULT),
        .prediction(prediction),
        .decode_error(decode_error),
        .cycles(cycles)
    );

    // Metadata registers returned in status.READ_DATA for opcode 7 (16 bits each):
    //  index   0       1        2      3       4        5      6
    //       +-------+--------+------+-------+--------+------+--------+
    //       | ver=2 | max D  |max E | max O | used D |used E| used O |
    //       +-------+--------+------+-------+--------+------+--------+
    //  index   7       8       9      10      11      12      13     14
    //       +-------+-------+-------+-------+-------+-------+-------+-------+
    //       | valid |gen LO |gen HI |pred LO|pred HI|cyc LO |cyc HI | error |
    //       +-------+-------+-------+-------+-------+-------+-------+-------+
    // valid (index 7) and error (index 14) use bit 0 with bits 15:1 forced to 0.
    // Each HI/LO pair reconstructs {HI[15:0], LO[15:0]}. Any index > 14 errors.
    always_comb begin
        // Require every 16-bit word covering 0..detector_count-1 to be written before decode.
        all_words_written = 1;
        for (integer w = 0; w < WORDS; w = w + 1) begin
            if (w * 16 < detector_count && !written_words[w])
                all_words_written = 0;
        end
        metadata_valid = 1;
        metadata = 0;
        case (ctrl[23:16])
            0: metadata = 2;
            1: metadata = 16'(MAX_DETECTORS);
            2: metadata = 16'(MAX_EDGES);
            3: metadata = 16'(MAX_OBSERVABLES);
            4: metadata = detector_count;
            5: metadata = edge_count;
            6: metadata = observable_count;
            7: metadata = {15'b0, configured};
            8: metadata = generation[15:0];
            9: metadata = generation[31:16];
            10: metadata = saved_prediction[15:0];
            11: metadata = saved_prediction[31:16];
            12: metadata = saved_cycles[15:0];
            13: metadata = saved_cycles[31:16];
            14: metadata = {15'b0, saved_error};
            default: metadata_valid = 0;
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            status <= 0;
            shot <= 0;
            written_words <= 0;
            request_bit <= 0;
            request_opcode <= 0;
            generation <= 0;
            saved_prediction <= 0;
            saved_cycles <= 0;
            saved_error <= 0;
            result_complete <= 0;
            for (k = 0; k < 8; k = k + 1)
                staging[k] <= 0;
        end else begin
            case (state)
                IDLE: begin
                    // A toggle on ctrl[31] signals a new request from the ARM PS.
                    if (ctrl[31] != status[31]) begin
                        request_bit <= ctrl[31];
                        request_opcode <= ctrl[27:24];
                        // Commands that do not take an index (ops 2, 3, 4, 6, 8)
                        // must pass INDEX == 0; reject nonzero indices immediately.
                        if ((ctrl[27:24] == 2 || ctrl[27:24] == 3
                            || ctrl[27:24] == 4 || ctrl[27:24] == 6
                            || ctrl[27:24] == 8) && ctrl[23:16] != 0) begin
                            status <= {ctrl[31], result_complete, 1'b1, 29'b0};
                        end else case (ctrl[27:24])
                            // Op 1: stage a 16-bit parameter for graph begin/append.
                            1: begin
                                if (ctrl[23:16] < 8) begin
                                    staging[ctrl[23:16]] <= ctrl[15:0];
                                    status <= {ctrl[31], result_complete, 1'b0, 29'b0};
                                end else begin
                                    status <= {ctrl[31], result_complete, 1'b1, 29'b0};
                                end
                            end
                            // Op 2: start a fresh graph upload and clear cached shot/result state.
                            2: begin
                                shot <= 0;
                                written_words <= 0;
                                result_complete <= 0;
                                saved_prediction <= 0;
                                saved_cycles <= 0;
                                saved_error <= 0;
                                state <= BEGIN_CONFIG;
                            end
                            // Op 3: append one staged edge record to the decoder core.
                            3: state <= APPEND_EDGE;
                            // Op 4: commit the staged graph in the decoder core.
                            4: state <= COMMIT_CONFIG;
                            // Op 5: write one 16-bit syndrome slice; reject out-of-range
                            // words or nonzero padding bits past detector_count.
                            5: begin
                                if (!configured || ctrl[23:16] >= WORDS
                                    || 16 * ctrl[23:16] >= detector_count
                                    || (ctrl[15:0] >> (detector_count - 16 * ctrl[23:16])) != 0) begin
                                    status <= {ctrl[31], result_complete, 1'b1, 29'b0};
                                end else begin
                                    shot[16*ctrl[23:16]+:16] <= ctrl[15:0];
                                    written_words[ctrl[23:16]] <= 1;
                                    status <= {ctrl[31], result_complete, 1'b0, 29'b0};
                                end
                            end
                            // Op 6: launch a decode once every active syndrome word has been written.
                            6: begin
                                if (!configured || !all_words_written) begin
                                    status <= {ctrl[31], result_complete, 1'b1, 29'b0};
                                end else begin
                                    result_complete <= 0;
                                    state <= LAUNCH;
                                    // Clear written_words so the next shot cannot reuse stale slices.
                                    written_words <= 0;
                                end
                            end
                            // Op 7: return the selected 16-bit metadata register in READ_DATA.
                            7: begin
                                status <= {ctrl[31], result_complete, !metadata_valid, 13'b0, metadata};
                            end
                            // Op 8: abort any in-flight shot and clear cached results (keeps graph).
                            8: state <= ABORT_SHOT;
                            default: begin
                                status <= {ctrl[31], result_complete, 1'b1, 29'b0};
                            end
                        endcase
                    end
                end
                // Pulse cfg_begin / cfg_write / cfg_commit for one cycle, then await cfg_ack.
                BEGIN_CONFIG, APPEND_EDGE, COMMIT_CONFIG: begin
                    state <= WAIT_CONFIG;
                end
                WAIT_CONFIG: begin
                    if (cfg_ack) begin
                        status <= {request_bit, result_complete, cfg_error, 29'b0};
                        if (request_opcode == 4 && !cfg_error)
                            generation <= generation + 1;
                        state <= IDLE;
                    end
                end
                // Assert in_valid until the core accepts the syndrome, then wait for out_valid.
                LAUNCH: begin
                    if (in_ready)
                        state <= WAIT_RESULT;
                end
                WAIT_RESULT: begin
                    if (out_valid) begin
                        saved_prediction <= 32'(prediction);
                        saved_cycles <= cycles;
                        saved_error <= decode_error;
                        result_complete <= 1;
                        status <= {request_bit, 1'b1, decode_error, 29'b0};
                        state <= IDLE;
                    end
                end
                // Pulse shot_abort for one cycle, clear cached shot state, then acknowledge.
                ABORT_SHOT: begin
                    shot <= 0;
                    written_words <= 0;
                    saved_prediction <= 0;
                    saved_cycles <= 0;
                    saved_error <= 0;
                    result_complete <= 0;
                    state <= ABORT_ACK;
                end
                ABORT_ACK: begin
                    status <= {request_bit, 31'b0};
                    state <= IDLE;
                end
                default: begin
                    status <= {request_bit, 1'b0, 1'b1, 29'b0};
                    state <= IDLE;
                end
            endcase
        end
    end
endmodule
