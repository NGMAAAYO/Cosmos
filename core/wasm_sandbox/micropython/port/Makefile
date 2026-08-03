include ../../py/mkenv.mk

QSTR_DEFS = qstrdefsport.h
MICROPY_ROM_TEXT_COMPRESSION = 0

include $(TOP)/py/py.mk

EMCC ?= emcc
CC = $(EMCC)
LD = $(EMCC)

INC += -I.
INC += -I$(TOP)
INC += -I$(BUILD)

CFLAGS += $(INC) -Wall -Werror -Wextra
CFLAGS += -Wno-unused-parameter -Wno-double-promotion -Wno-float-conversion
CFLAGS += -std=c11 -Oz -DNDEBUG -fdata-sections -ffunction-sections
CFLAGS += -DMICROPY_NLR_SETJMP=1 -fwasm-exceptions

LDFLAGS += -sSTANDALONE_WASM=1 -sSUPPORT_LONGJMP=wasm -fwasm-exceptions
LDFLAGS += -sFILESYSTEM=0 -sALLOW_MEMORY_GROWTH=0 -sERROR_ON_UNDEFINED_SYMBOLS=1
LDFLAGS += -sINITIAL_MEMORY=4194304 -sSTACK_SIZE=262144
LDFLAGS += -Wl,--no-entry -Wl,--gc-sections -Wl,--strip-all
LIBS = -lm

SRC_C = \
	main.c \
	extmod/modheapq.c \
	extmod/modrandom.c

SRC_QSTR += $(SRC_C)

OBJ += $(PY_CORE_O)
OBJ += $(addprefix $(BUILD)/, $(SRC_C:.c=.o))

all: $(BUILD)/cosmos_micropython.wasm

$(BUILD)/cosmos_micropython.wasm: $(OBJ)
	$(ECHO) "LINK $@"
	$(Q)$(LD) $(LDFLAGS) -o $@ $^ $(LIBS)

include $(TOP)/py/mkrules.mk
