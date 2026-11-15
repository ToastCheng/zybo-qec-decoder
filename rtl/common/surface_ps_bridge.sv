`timescale 1ns / 1ps
// Same-FCLK GPIO command mailbox. Generic 16-bit syndrome word loading.
module surface_ps_bridge #(
    parameter DETECTORS = 24,
    parameter EDGES = 78,
    parameter GRAPH_FILE = "qec/surface/graphs/d3_z_r3.mem"
) (
    input logic clk,
    input logic rst,
    input logic [31:0] ctrl,
    output logic [31:0] status
);
    // ctrl: [31] request toggle, [27:24] opcode, [23:16] index, [15:0] data.
    // status: [31] acknowledged toggle, [30] result, [29] error, [28] prediction,
    // [27:0] cycles. PS must keep command data stable until acknowledgement.
    localparam WORDS = (DETECTORS + 15) / 16;
    logic [WORDS*16-1:0] shot;
    logic in_valid;
    logic in_ready;
    logic out_valid;
    logic prediction;
    logic decode_error;
    logic reset_core;
    logic [31:0] cycles;
    logic request_bit;
    typedef enum logic [2:0] {
        IDLE,
        LAUNCH,
        WAIT_RESULT,
        RESET_ACK
    } state_t;
    state_t state = IDLE;
    // Commands are consumed only in IDLE; PS holds ctrl stable until status[31]
    // matches. LAUNCH holds valid until ready, WAIT_RESULT acknowledges completion.
    assign in_valid = state == LAUNCH;
    surface_decoder #(
        .DETECTORS(DETECTORS),
        .EDGES(EDGES),
        .GRAPH_FILE(GRAPH_FILE)
    ) core (
        .clk(clk),
        .rst(rst || reset_core),
        .in_valid(in_valid),
        .in_ready(in_ready),
        .syndrome(shot[DETECTORS-1:0]),
        .out_valid(out_valid),
        .out_ready(1'b1),
        .prediction(prediction),
        .decode_error(decode_error),
        .cycles(cycles)
    );
    always_ff @(posedge clk) begin
        if (rst) begin
            status <= 0;
            shot <= 0;
            reset_core <= 0;
            request_bit <= 0;
            state <= IDLE;
        end else begin
            reset_core <= 0;
            case (state)
                IDLE:
                if (ctrl[31] != status[31]) begin
                    request_bit <= ctrl[31];
                    case (ctrl[27:24])
                        // Opcode 1 loads little-endian 16-detector words; unused upper bits are ignored.
                        1: begin
                            if (ctrl[23:16] < WORDS) begin
                                shot[16*ctrl[23:16]+:16] <= ctrl[15:0];
                                status <= {ctrl[31], 3'b0, 28'b0};
                            end else status <= {ctrl[31], 1'b0, 1'b1, 1'b0, 28'b0};
                        end
                        2: begin
                            status[30:0] <= 0;
                            state <= LAUNCH;
                        end
                        3: begin
                            reset_core <= 1;
                            shot <= 0;
                            state <= RESET_ACK;
                        end
                        default: status <= {ctrl[31], 1'b0, 1'b1, 1'b0, 28'b0};
                    endcase
                end
                LAUNCH: if (in_ready) state <= WAIT_RESULT;
                // The mailbox carries only 28 cycle bits: overflow is reported as error.
                WAIT_RESULT:
                if (out_valid) begin
                    status <= {
                        request_bit,
                        1'b1,
                        (decode_error || (|cycles[31:28])),
                        prediction,
                        cycles[27:0]
                    };
                    state <= IDLE;
                end
                // Delay acknowledgement until the core has seen its synchronous reset pulse.
                RESET_ACK: begin
                    status <= {request_bit, 31'b0};
                    state  <= IDLE;
                end
                default: begin
                    state <= IDLE;
                    reset_core <= 1;
                end
            endcase
        end
    end
endmodule
