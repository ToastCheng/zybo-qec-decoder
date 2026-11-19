/* Connect PS UART1 to the same-clock AXI GPIO mailbox. */
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

/* SDT names the enabled UART1 XUARTPS_0; reject a different address. */
#if XPAR_XUARTPS_0_BASEADDR != 0xe0001000u
#error "Runtime firmware requires PS UART1 at 0xe0001000"
#endif
#if COUNTS_PER_SECOND < 1000
#error "Runtime millisecond deadlines require a counter frequency >= 1000 Hz"
#endif

#define QEC_UART_BASE XPAR_XUARTPS_0_BASEADDR
#define QEC_GPIO_BASE 0x41200000u
static XUartPs qec_platform_uart;

static inline void qec_platform_init(void)
{
    XUartPs_Config *config = XUartPs_LookupConfig(QEC_UART_BASE);
    /* Exit silently on UART failure to keep diagnostic text off the binary link. */
    if (config == NULL ||
        XUartPs_CfgInitialize(&qec_platform_uart, config,
                             config->BaseAddress) != 0 ||
        XUartPs_SetBaudRate(&qec_platform_uart, 115200u) != 0) {
        exit(EXIT_FAILURE);
    }
    XUartPs_SetOperMode(&qec_platform_uart, XUARTPS_OPER_MODE_NORMAL);
    /* Set GPIO directions without writing control data or creating a request toggle. */
    Xil_Out32(QEC_GPIO_BASE + 4u, 0u);
    Xil_Out32(QEC_GPIO_BASE + 12u, UINT32_MAX);
}

static inline void qec_platform_write_control(void *ignored, uint32_t value)
{
    (void)ignored;
    Xil_Out32(QEC_GPIO_BASE, value);
}

static inline uint32_t qec_platform_read_status(void *ignored)
{
    (void)ignored;
    return Xil_In32(QEC_GPIO_BASE + 8u);
}

static inline uint32_t qec_platform_now_ms(void *ignored)
{
    XTime ticks;
    (void)ignored;
    /* Split ticks before scaling to avoid overflow; unsigned milliseconds wrap. */
    XTime_GetTime(&ticks);
    /* Parenthesize the BSP CPU_HZ/2 macro before division. */
    return (uint32_t)(ticks / (COUNTS_PER_SECOND)) * 1000u +
           (uint32_t)((ticks % (COUNTS_PER_SECOND)) * 1000u / (COUNTS_PER_SECOND));
}

static inline int qec_platform_read_byte(void)
{
    if (!XUartPs_IsReceiveData(QEC_UART_BASE)) {
        return -1;
    }
    return (int)(uint8_t)XUartPs_ReadReg(QEC_UART_BASE, XUARTPS_FIFO_OFFSET);
}

static inline void qec_platform_emit(void *ignored, const uint8_t *data,
                                     size_t length)
{
    (void)ignored;
    for (size_t i = 0; i < length; ++i) {
        XUartPs_SendByte(QEC_UART_BASE, data[i]);
    }
    /* Wait for both the FIFO and transmitter to drain. */
    while (!XUartPs_IsTransmitFifoEmpty(QEC_UART_BASE) ||
           XUartPs_IsTransmitActive(QEC_UART_BASE)) {
    }
}

#endif
