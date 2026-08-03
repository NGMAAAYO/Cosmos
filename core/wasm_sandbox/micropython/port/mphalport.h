#pragma once

#include <stddef.h>
#include <stdint.h>

#include "py/obj.h"

#define mp_hal_stdin_rx_chr() (0)

mp_uint_t mp_hal_stdout_tx_strn(const char *str, size_t len);
mp_uint_t mp_hal_ticks_ms(void);
mp_uint_t mp_hal_ticks_us(void);
mp_uint_t mp_hal_ticks_cpu(void);
