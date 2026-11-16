`timescale 1ns / 1ps
module top_qec_soc #(
    parameter integer MAX_DETECTORS = 128,
    parameter integer MAX_EDGES = 512,
    parameter integer MAX_OBSERVABLES = 32
) (
    output logic [3:0] led,
    inout wire [14:0] DDR_addr,
    inout wire [2:0] DDR_ba,
    inout wire DDR_cas_n,
    inout wire DDR_ck_n,
    inout wire DDR_ck_p,
    inout wire DDR_cke,
    inout wire DDR_cs_n,
    inout wire [3:0] DDR_dm,
    inout wire [31:0] DDR_dq,
    inout wire [3:0] DDR_dqs_n,
    inout wire [3:0] DDR_dqs_p,
    inout wire DDR_odt,
    inout wire DDR_ras_n,
    inout wire DDR_reset_n,
    inout wire DDR_we_n,
    inout wire FIXED_IO_ddr_vrn,
    inout wire FIXED_IO_ddr_vrp,
    inout wire [53:0] FIXED_IO_mio,
    inout wire FIXED_IO_ps_clk,
    inout wire FIXED_IO_ps_porb,
    inout wire FIXED_IO_ps_srstb
);
    // The PS wrapper supplies DDR, MIO and the shared GPIO/decoder clock.
    wire clk;
    wire resetn;
    wire [31:0] ctrl;
    wire [31:0] status;
    system_wrapper ps (
        .DDR_addr(DDR_addr),
        .DDR_ba(DDR_ba),
        .DDR_cas_n(DDR_cas_n),
        .DDR_ck_n(DDR_ck_n),
        .DDR_ck_p(DDR_ck_p),
        .DDR_cke(DDR_cke),
        .DDR_cs_n(DDR_cs_n),
        .DDR_dm(DDR_dm),
        .DDR_dq(DDR_dq),
        .DDR_dqs_n(DDR_dqs_n),
        .DDR_dqs_p(DDR_dqs_p),
        .DDR_odt(DDR_odt),
        .DDR_ras_n(DDR_ras_n),
        .DDR_reset_n(DDR_reset_n),
        .DDR_we_n(DDR_we_n),
        .FIXED_IO_ddr_vrn(FIXED_IO_ddr_vrn),
        .FIXED_IO_ddr_vrp(FIXED_IO_ddr_vrp),
        .FIXED_IO_mio(FIXED_IO_mio),
        .FIXED_IO_ps_clk(FIXED_IO_ps_clk),
        .FIXED_IO_ps_porb(FIXED_IO_ps_porb),
        .FIXED_IO_ps_srstb(FIXED_IO_ps_srstb),
        .gpio_io_o_0(ctrl),
        .gpio2_io_i_0(status),
        .FCLK_CLK0_0(clk),
        .peripheral_aresetn_0(resetn)
    );
    // Invert the active-low peripheral reset for the decoder bridge.
    ps_bridge #(
        .MAX_DETECTORS(MAX_DETECTORS),
        .MAX_EDGES(MAX_EDGES),
        .MAX_OBSERVABLES(MAX_OBSERVABLES)
    ) bridge (
        .clk(clk),
        .rst(!resetn),
        .ctrl(ctrl),
        .status(status)
    );
    // User LEDs directly expose the last mailbox status, not logical success.
    //       +-------------+-------------+-------------+------------------+
    // LED   | 3 (D18)     | 2 (G14)     | 1 (M15)     | 0 (M14)          |
    //       +-------------+-------------+-------------+------------------+
    // bit   | status[31]  | status[30]  | status[29]  | status[0]        |
    // role  | ACK phase   | decode DONE | op ERROR    | READ_DATA bit 0  |
    //       +-------------+-------------+-------------+------------------+
    // LED0 changes meaning with metadata INDEX; it is not prediction bit 0.
    // DONE can be high on an errored decode. See docs/decoder-design.md.
    assign led = {status[31:29], status[0]};
endmodule
