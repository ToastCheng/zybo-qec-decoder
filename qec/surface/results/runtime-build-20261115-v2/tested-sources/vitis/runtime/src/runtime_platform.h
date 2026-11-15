/* Zybo Z7 PS UART1 and same-FCLK AXI GPIO runtime mailbox. */
#ifndef QEC_RUNTIME_PLATFORM_H
#define QEC_RUNTIME_PLATFORM_H

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include "xparameters.h"
#include "xil_io.h"
#include "xuartps.h"
#include "xuartps_hw.h"
#include "xiltimer.h"

/* SDT enumerates the sole enabled UART1 as XUARTPS_0, not UART0. Refuse
 * an incompatible hardware handoff rather than silently using another port. */
#if XPAR_XUARTPS_0_BASEADDR != 0xe0001000u
#error "Runtime firmware requires PS UART1 at 0xe0001000"
#endif
#if COUNTS_PER_SECOND < 1000
#error "Runtime millisecond deadlines require a counter frequency >= 1000 Hz"
#endif

#define RUNTIME_UART_BASE XPAR_XUARTPS_0_BASEADDR
#define RUNTIME_GPIO_BASE 0x41200000u
static XUartPs runtime_platform_uart;

static inline void runtime_platform_init(void)
{
    XUartPs_Config *config = XUartPs_LookupConfig(RUNTIME_UART_BASE);
    /* The binary UART must remain silent even on failure. Do not continue
     * with uninitialized peripherals; the BSP exit path stops this process. */
    if (config == NULL ||
        XUartPs_CfgInitialize(&runtime_platform_uart, config,
                              config->BaseAddress) != 0 ||
        XUartPs_SetBaudRate(&runtime_platform_uart, 115200u) != 0) {
        exit(EXIT_FAILURE);
    }
    XUartPs_SetOperMode(&runtime_platform_uart, XUARTPS_OPER_MODE_NORMAL);
    /* Channel 1 is control/output; channel 2 is status/input. Never write
     * control DATA during init: that would manufacture a request toggle.
     * main adopts the settled acknowledgement phase, without resetting PL. */
    Xil_Out32(RUNTIME_GPIO_BASE + 4u, 0u);
    Xil_Out32(RUNTIME_GPIO_BASE + 12u, UINT32_MAX);
}

static inline void runtime_platform_write_control(void *ignored, uint32_t value)
{
    (void)ignored;
    Xil_Out32(RUNTIME_GPIO_BASE, value);
}

static inline uint32_t runtime_platform_read_status(void *ignored)
{
    (void)ignored;
    return Xil_In32(RUNTIME_GPIO_BASE + 8u);
}

static inline uint32_t runtime_platform_now_ms(void *ignored)
{
    XTime ticks;
    (void)ignored;
    /* xiltimer is initialized by its BSP constructor. Split before scaling:
     * neither ticks*1000 overflow nor rounded counts/ms clock drift is safe.
     * The uint32 result intentionally wraps; main uses unsigned subtraction. */
    XTime_GetTime(&ticks);
    /* Generated COUNTS_PER_SECOND expands to CPU_HZ/2 without parentheses. */
    return (uint32_t)(ticks / (COUNTS_PER_SECOND)) * 1000u +
           (uint32_t)((ticks % (COUNTS_PER_SECOND)) * 1000u / (COUNTS_PER_SECOND));
}

static inline int runtime_platform_read_byte(void)
{
    if (!XUartPs_IsReceiveData(RUNTIME_UART_BASE)) {
        return -1;
    }
    return (int)(uint8_t)XUartPs_ReadReg(RUNTIME_UART_BASE, XUARTPS_FIFO_OFFSET);
}

static inline void runtime_platform_emit(void *ignored, const uint8_t *data,
                                          size_t length)
{
    (void)ignored;
    for (size_t i = 0; i < length; ++i) {
        XUartPs_SendByte(RUNTIME_UART_BASE, data[i]);
    }
    /* SendByte waits for FIFO room, not transmission completion. Drain both
     * the FIFO and shifter before returning the caller's stack frame. */
    while (!XUartPs_IsTransmitFifoEmpty(RUNTIME_UART_BASE) ||
           XUartPs_IsTransmitActive(RUNTIME_UART_BASE)) {
    }
}

#endif
