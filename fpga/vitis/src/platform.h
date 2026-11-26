/*
 * Zybo Z7-10 standalone hardware adapter included by main.c on board builds.
 *
 * Connects the firmware parser to:
 *   - PS UART1 at 0xE0001000 (115200 baud, non-blocking RX poll, drain-on-TX)
 *   - Dual-channel AXI GPIO at 0x41200000 (channel 1 out = ctrl, channel 2 in = status)
 *   - Zynq global timer via XTime_GetTime() converted to wrapping 32-bit milliseconds
 */
#ifndef QEC_PLATFORM_H
#define QEC_PLATFORM_H

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include "xparameters.h"
#include "xil_io.h"
#include "xuartps.h"
#include "xuartps_hw.h"
#include "xiltimer.h"

/* SDT maps the enabled Zybo USB-UART (PS UART1) to XUARTPS_0 at 0xE0001000. */
#if XPAR_XUARTPS_0_BASEADDR != 0xe0001000u
#error "Runtime firmware requires PS UART1 at 0xe0001000"
#endif
#if COUNTS_PER_SECOND < 1000
#error "Runtime millisecond deadlines require a counter frequency >= 1000 Hz"
#endif

#define QEC_UART_BASE XPAR_XUARTPS_0_BASEADDR
/* Fixed AXI GPIO base address assigned in fpga/scripts/bd/soc.tcl. */
#define QEC_GPIO_BASE 0x41200000u
static XUartPs qec_platform_uart;

/* Configure PS UART1 at 115200 baud and set AXI GPIO channel directions. */
static inline void qec_platform_init(void)
{
    XUartPs_Config *config = XUartPs_LookupConfig(QEC_UART_BASE);
    /* Never print text on init failure; stdout shares this binary UART link. */
    if (config == NULL ||
        XUartPs_CfgInitialize(&qec_platform_uart, config,
                             config->BaseAddress) != 0 ||
        XUartPs_SetBaudRate(&qec_platform_uart, 115200u) != 0) {
        exit(EXIT_FAILURE);
    }
    XUartPs_SetOperMode(&qec_platform_uart, XUARTPS_OPER_MODE_NORMAL);
    /* Set tri-state registers only (+0x04 ch1 out, +0x0C ch2 in) without writing
     * ch1 data so we do not trigger a spurious REQ toggle on startup.
     */
    Xil_Out32(QEC_GPIO_BASE + 4u, 0u);
    Xil_Out32(QEC_GPIO_BASE + 12u, UINT32_MAX);
}

/* Write the 32-bit mailbox command word (including REQ toggle) to GPIO channel 1. */
static inline void qec_platform_write_control(void *ignored, uint32_t value)
{
    (void)ignored;
    Xil_Out32(QEC_GPIO_BASE, value);
}

/* Read the 32-bit mailbox status word (ACK, DONE, ERROR, READ_DATA) from GPIO channel 2. */
static inline uint32_t qec_platform_read_status(void *ignored)
{
    (void)ignored;
    return Xil_In32(QEC_GPIO_BASE + 8u);
}

/* Convert the 64-bit global timer tick count into wrapping 32-bit milliseconds. */
static inline uint32_t qec_platform_now_ms(void *ignored)
{
    XTime ticks;
    (void)ignored;
    XTime_GetTime(&ticks);
    /* Split whole seconds and remainder before scaling by 1000 to prevent overflow;
     * parenthesize COUNTS_PER_SECOND because the BSP defines it as an expression.
     */
    return (uint32_t)(ticks / (COUNTS_PER_SECOND)) * 1000u +
           (uint32_t)((ticks % (COUNTS_PER_SECOND)) * 1000u / (COUNTS_PER_SECOND));
}

/* Return one received UART byte (0..255), or -1 if the RX FIFO is empty. */
static inline int qec_platform_read_byte(void)
{
    if (!XUartPs_IsReceiveData(QEC_UART_BASE)) {
        return -1;
    }
    return (int)(uint8_t)XUartPs_ReadReg(QEC_UART_BASE, XUARTPS_FIFO_OFFSET);
}

/* Transmit a complete binary reply frame and wait until the UART shifter drains. */
static inline void qec_platform_emit(void *ignored, const uint8_t *data,
                                     size_t length)
{
    (void)ignored;
    for (size_t i = 0; i < length; ++i) {
        XUartPs_SendByte(QEC_UART_BASE, data[i]);
    }
    /* Wait for both the TX FIFO and the shift register to empty before returning. */
    while (!XUartPs_IsTransmitFifoEmpty(QEC_UART_BASE) ||
           XUartPs_IsTransmitActive(QEC_UART_BASE)) {
    }
}

#endif
