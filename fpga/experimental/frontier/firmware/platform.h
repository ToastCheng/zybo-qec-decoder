/* Zynq-7000 standalone BSP adapter for PS UART1 and the PL AXI GPIO mailbox. */
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

/* The SDT BSP maps the sole enabled UART (PS UART1) to XUARTPS_0. */
#if XPAR_XUARTPS_0_BASEADDR != 0xe0001000u
#error "Runtime firmware requires PS UART1 at 0xe0001000"
#endif
#if COUNTS_PER_SECOND < 1000
#error "Runtime millisecond deadlines require a counter frequency >= 1000 Hz"
#endif

/* PS UART1 base address (host serial link). */
#define QEC_UART_BASE XPAR_XUARTPS_0_BASEADDR
/* Dual-channel AXI GPIO base address from the Zybo block design. */
#define QEC_GPIO_BASE 0x41200000u
/* UART driver instance for initialization; byte I/O hits registers directly. */
static XUartPs qec_platform_uart;

/* Initialize UART1 at 115200 baud and set AXI GPIO ch1=output, ch2=input. */
static inline void qec_platform_init(void)
{
    XUartPs_Config *config = XUartPs_LookupConfig(QEC_UART_BASE);
    /* Fail silently rather than printing text onto the binary protocol link. */
    if (config == NULL ||
        XUartPs_CfgInitialize(&qec_platform_uart, config,
                             config->BaseAddress) != 0 ||
        XUartPs_SetBaudRate(&qec_platform_uart, 115200u) != 0) {
        exit(EXIT_FAILURE);
    }
    XUartPs_SetOperMode(&qec_platform_uart, XUARTPS_OPER_MODE_NORMAL);
    /* Configure tri-state directions only, without touching ch1 data/toggle. */
    Xil_Out32(QEC_GPIO_BASE + 4u, 0u);
    Xil_Out32(QEC_GPIO_BASE + 12u, UINT32_MAX);
}

/* Write the 32-bit mailbox ctrl word (with REQ toggle) to GPIO channel 1. */
static inline void qec_platform_write_control(void *ignored, uint32_t value)
{
    (void)ignored;
    Xil_Out32(QEC_GPIO_BASE, value);
}

/* Read the 32-bit mailbox status word (ACK/DONE/ERROR/READ_DATA) from channel 2. */
static inline uint32_t qec_platform_read_status(void *ignored)
{
    (void)ignored;
    return Xil_In32(QEC_GPIO_BASE + 8u);
}

/* Convert the 64-bit global timer to a wrapping 32-bit millisecond count. */
static inline uint32_t qec_platform_now_ms(void *ignored)
{
    XTime ticks;
    (void)ignored;
    /* Divide seconds and remainder separately so multiplying by 1000 cannot overflow. */
    XTime_GetTime(&ticks);
    /* Parenthesize COUNTS_PER_SECOND because the BSP defines it as CPU_HZ/2. */
    return (uint32_t)(ticks / (COUNTS_PER_SECOND)) * 1000u +
           (uint32_t)((ticks % (COUNTS_PER_SECOND)) * 1000u / (COUNTS_PER_SECOND));
}

/* Non-blocking UART read: returns 0..255 or -1 if the RX FIFO is empty. */
static inline int qec_platform_read_byte(void)
{
    if (!XUartPs_IsReceiveData(QEC_UART_BASE)) {
        return -1;
    }
    return (int)(uint8_t)XUartPs_ReadReg(QEC_UART_BASE, XUARTPS_FIFO_OFFSET);
}

/* Transmit a full reply frame and wait until the UART shifter has drained. */
static inline void qec_platform_emit(void *ignored, const uint8_t *data,
                                     size_t length)
{
    (void)ignored;
    for (size_t i = 0; i < length; ++i) {
        XUartPs_SendByte(QEC_UART_BASE, data[i]);
    }
    /* Wait for both TX FIFO and active shift register to empty. */
    while (!XUartPs_IsTransmitFifoEmpty(QEC_UART_BASE) ||
           XUartPs_IsTransmitActive(QEC_UART_BASE)) {
    }
}

#endif
