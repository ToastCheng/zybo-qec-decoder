`timescale 1ns / 1ps
// Zybo Z7-10 board top level.
// Connects the generated Zynq-7000 PS block design (`system_wrapper`) to
// `ps_bridge` over a 32-bit AXI GPIO mailbox on the shared 100 MHz fabric
// clock, and wires four mailbox status bits directly to the board user LEDs.
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
    // Zynq PS block design: provides DDR, MIO/UART1, the 100 MHz fabric clock,
    // an active-low peripheral reset, and the dual-channel AXI GPIO mailbox.
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
    // ps_bridge expects an active-high synchronous reset; invert peripheral_aresetn_0.
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
    // Board user LEDs mirror live mailbox status bits (not logical decode success):
    //       +-------------+-------------+-------------+------------------+
    // LED   | 3 (D18)     | 2 (G14)     | 1 (M15)     | 0 (M14)          |
    //       +-------------+-------------+-------------+------------------+
    // bit   | status[31]  | status[30]  | status[29]  | status[0]        |
    // role  | ACK phase   | decode DONE | op ERROR    | READ_DATA bit 0  |
    //       +-------------+-------------+-------------+------------------+
    // Notes:
    // - LED3 toggles on every acknowledged mailbox command (matches ctrl[31]).
    // - LED2 (DONE) is high whenever a decode has finished, including errored decodes.
    // - LED1 (ERROR) reflects only the latest command ack (cleared by a valid metadata read).
    // - LED0 shows bit 0 of the last metadata read (e.g. saved_error after reading index 14),
    //   not prediction bit 0. See docs/decoder-design.md.
    assign led = {status[31:29], status[0]};
endmodule
