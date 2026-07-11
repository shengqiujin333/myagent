Now I have enough information. Let me write the comprehensive context.md.

```markdown
# Build Context

## Goal

完成电池内阻测量系统的固件重构与开发。目标硬件为 **STM32G030F6P6** (TSSOP-20封装)，使用 **Keil MDK-ARM** (ArmClang V6.19) 编译。系统功能：通过PWM产生1kHz方波 → RC滤波生成正弦波 → 运放恒流源向电池注入交流电流 → 同步采集电池两端电压，计算内阻。支持多电池手拉手UART级联（一主多从）、DS18B20温度测量、异常数据识别算法，全部采用状态机实现，禁止阻塞。

## Source Materials

### Directory Overview

| Directory | Summary |
|-----------|---------|
| `battery_re/Core/Inc` | 头文件：`stm32g0xx_hal_conf.h` (HAL模块配置)、`stm32g0xx_it.h` (中断声明) |
| `battery_re/Core/Src` | 源文件：`stm32g0xx_it.c` (中断服务)、`system_stm32g0xx.c` (系统时钟配置，HSE 8MHz→PLL→64MHz)。**main.c 和 stm32g0xx_hal_msp.c 已被删除，需要重建** |
| `battery_re/Drivers/CMSIS` | CMSIS Core/Device/DSP/RTOS库，包含 `arm_cortexM0l_math.lib` (DSP数学库已链接) |
| `battery_re/Drivers/STM32G0xx_HAL_Driver` | STM32G0 HAL驱动：ADC、RCC、GPIO、DMA、TIM、UART、FLASH、PWR、EXTI、IWDG等 |
| `battery_re/MDK-ARM` | Keil项目文件 `battery_re.uvprojx`，启动文件 `startup_stm32g030xx.s`，构建日志，编译产物 |
| `.document-reader/netlist` | 网表文件(TEL格式→Markdown)，包含完整电路连接信息 |
| `.document-reader/BOM` | BOM物料清单 (Excel→Markdown) |
| `.document-reader/DS12991` | STM32G030x6/x8 数据手册 (PDF→Markdown)，298913行 |
| `.understand-anything` | 中间分析产物，非直接项目文件 |

### Key Files Inspected

- **`user_req.txt`** — 用户需求文档。核心功能、引脚分配、协议要求、编译命令等完整描述。
- **`Netlist_Schematic1_2026-05-25.tel`** — 网表文件，包含所有网络连接、元器件引脚映射。
- **`battery_re/MDK-ARM/battery_re.uvprojx`** — Keil项目配置：STM32G030F6Px，Flash 64KB (0x08000000-0x00010000)，RAM 8KB (0x20000000-0x20002000)，ArmClang V6.19，USE_HAL_DRIVER,STM32G030xx 宏定义。
- **`battery_re/Core/Src/system_stm32g0xx.c`** — 系统时钟：HSE 8MHz → PLL (M=1,N=16,R=2) → SysClk=64MHz。Flash 2等待周期，预取使能。
- **`battery_re/Core/Src/stm32g0xx_it.c`** — 中断处理框架：已声明弱函数 `SCHED_IncTick()` 和 `UART_IRQHandler()` 供子模块替换。已使能的中断：DMA1_CH1、ADC1、TIM1_BRK_UP_TRG_COM、TIM3、TIM14、USART1、USART2。
- **`battery_re/Core/Inc/stm32g0xx_hal_conf.h`** — 已启用HAL模块：ADC、TIM、UART、GPIO、EXTI、DMA、RCC、FLASH、PWR、CORTEX、IWDG。
- **`battery_re/Core/Inc/stm32g0xx_it.h`** — 中断声明文件。
- **`battery_re/MDK-ARM/startup_stm32g030xx.s`** — 启动文件。Stack=0x400, Heap=0x200。
- **`battery_re/MDK-ARM/battery_re.map`** — 链接映射(来自已删main.c的编译产物)，可推断之前的全局变量符号: `huart1`, `huart2`, `htim3`, `htim14`, `hadc1`, `hdma_adc1`。
- **`battery_re/MDK-ARM/build_log.txt`** — 最后一次成功编译日志 (0 Error, 0 Warning)。Code=3432, RO-data=288, RW-data=12, ZI-data=1660。
- **`battery_re/MDK-ARM/rebuild_all_result.log`** — 全量重建日志 (0 Error, 0 Warning)。Code=5192, RO-data=288, RW-data=12, ZI-data=1580。
- **`.document-reader/BOM/document.md`** — 完整BOM表。

## Task Requirements

### Functional behavior
- PWM产生1kHz方波 → RC滤波 → 跟随器 → 运放恒流源输出正弦波，向电池注入交流电流
- 同步采集电池两端电压（与注入电流相位同步），计算内阻
- 每1分钟测量一次电池内阻
- DS18B20温度测量，每30秒一次
- 多电池UART级联：一主多从，主机分配从机地址，主机轮询所有从机数据（电压、电流、内阻、温度等）
- MCU Pin12 (M_S) 作为主从判断：上拉输入，低电平→从机，高电平→主机，开机判断一次后切为输入省电
- 采样率10kHz采集电池两端电压，与电流相位同步
- 需校准注入电流与电压之间的相位差
- 需支持实际电阻多点校准
- 异常数据识别算法：滤除充电/放电逆变器干扰
- 全部使用状态机实现，禁止阻塞

### Interfaces and protocols
- **UART1** (主机端): TX连下一节电池从机的RX，作为主机发送指令
- **UART2** (从机端): 接收前级主机命令
- **UART级联协议**: 自定义协议，主机可分配地址、轮询数据
- **DS18B20**: DQ线，单总线协议，30秒测量一次
- **M_S引脚**: GPIO输入，开机时判断主从身份

### Outputs and indicators
- 内阻值（通过UART上报）
- 注入电流值
- 电池两端电压
- 温度值
- 异常数据标志

### Timing and performance
- PWM频率: 1kHz
- ADC采样率: 10kHz，与PWM相位同步
- 测量周期: 1分钟/次
- 温度测量: 30秒/次
- 系统时钟: 64MHz (HSE 8MHz → PLL)
- UART波特率: 未明确指定，[推断] 通常使用115200

### Tests and acceptance criteria
- 通过Keil编译 (UV4.exe -j0 -b)
- 通过UART串口验证通信协议
- 能正确测量并计算内阻

## Hardware Connection

### MCU / SoC
- **Part number**: STM32G030F6P6TR (U3-1)
- **Core / architecture**: ARM Cortex-M0+, 32-bit, up to 64MHz
- **Package**: TSSOP-20 (6.4×4.4mm)
- **Flash**: 32KB (0x08000000, size 0x00010000)
- **SRAM**: 8KB (0x20000000, size 0x00002000)

### Debug / Flash Interface
- **Protocol**: SWD (Serial Wire Debug)
- **Connector**: H5 (HDR-TH_4P-P2.54-V-M, B-2100S04P-A110)
- **Pinout**: H5.3 → SWDIO (MCU pin 18/PA13), H5.4 → SWCLK (MCU pin 19/PA14), H5.1 → 3.3V
- **Required tools**: J-Link / ST-Link / PyOCD (pyocd flash -t stm32f103c8 — [注意] 命令中目标器件与实际不符，应为 stm32g030f6)

### Peripheral Wiring

| Signal | MCU Pin (TSSOP20) | MCU Function | Target Device / Module | Direction | Notes |
|--------|-------------------|--------------|----------------------|-----------|-------|
| UART1_TX | 20 | PA15 / USART1_TX | CN4.3 → 隔离 → 下一级从机RX | OUT | 级联主机发送 |
| UART1_RX | 1 | PA10 / USART1_RX | CN4.2 → 隔离 → 上/下一级 | IN | 级联主机接收 |
| UART2_TX | 9 | PA2 / USART2_TX | U5 (CA-IS3721LS) pin 6 | OUT | 隔离后到CN3 |
| UART2_RX | 10 | PA3 / USART2_RX | U5 (CA-IS3721LS) pin 7 | IN | 隔离来自CN3 |
| TIM3_CH3 | 15 | PB0 / TIM3_CH3 | R21 → 后级RC滤波电路 | OUT | 1kHz PWM输出 |
| VOLT_ADC | 8 | PA7 / ADC_IN7 | 电池电压采样网络 | IN | 分压后ADC输入 |
| CURRENT_ADC | 13 | PA6... [推断] / 实际对应... | U11 (OPA) pin 1 → 电流采样 | IN | 注入电流ADC输入 |
| RES_ADC | 14 | PA5... [推断] / 实际对应... | U10 (OPA) pin 7 → 电阻电压 | IN | 内阻测量ADC输入 |
| DQ | 11 | PA4 / GPIO | H6.2 → DS18B20 DQ | I/O | 4.7kΩ上拉(R6) |
| M_S | 12 | PA5 / GPIO | R9 (100K) 上拉到3.3V + 外部拉低 | IN | 主从识别，开机采样 |
| NRST | 6 | NRST | U6 (复位芯片) | IN | 外部复位 |
| SWDIO | 18 | PA13 | H5.3 | I/O | SWD调试 |
| SWCLK | 19 | PA14 | H5.4 | I/O | SWD调试 |
| VDD | 4 | VDDA | 3.3V | POWER |  |
| VSS | 5, 7 | VSSA, VSS | ISOGND | POWER | 数字/模拟地隔离 |

**注意**: 以上MCU引脚编号（U3-1.x: 1,4,5,6,7,8,9,10,11,12,13,14,15,18,19,20）直接取自网表。物理TSSOP20封装引脚与功能之间的映射基于标准STM32G030F6P6 pinout推断，因datasheet PDF解析不完整，部分映射存在不确定性（见下方）。

### Key Components (from BOM)
| Ref | Part | Package | Function |
|-----|------|---------|----------|
| U3-1 | STM32G030F6P6TR | TSSOP-20 | MCU |
| U5 | CA-IS3721LS | SOIC-8 | 数字隔离器 (用于UART隔离) |
| OP1 | LM258DT | SOIC-8 | 运算放大器 (跟随器/恒流源) |
| U1 | TLV431AIDBZR | SOT-23-3 | 可调精密并联稳压器 |
| U1-1 | VPS8701B | SOT-23-6 | [推断] 隔离DC-DC电源模块 |
| U2-1 | XC6206P332MR-G | SOT-23-3 | 3.3V LDO稳压器 |
| U8,U9,U10,U11 | (未标注型号) | SOP-8 | 运放 (OPA) |
| T1-1 | VPT87DFB01B | XFMR-SMD | 变压器 (用于隔离电源) |
| Q1,Q2,Q3,Q4 | SS8050 | SOT-23-3 | NPN三极管 |
| D1 | (SMB) | SMB | TVS/整流管 |
| D1-1 | SMAJ15CA | SMA | TVS 15V |
| D2-1,D3-1 | RB160M-30 | SOD-123 | 肖特基二极管 30V |
| R16 | 0.1Ω | R0805 | 采样电阻 (电流检测) |
| F1-1 | 0603L050YR | F0603 | 自恢复保险丝 |
| H6 | xh2_54-3p | 3-pin | DS18B20接口 (DQ/GND/3.3V) |
| CN1,CN2 | HT396V-3.96-2P | 2-pin | 电池连接端子 (+12V/GND) |
| CN3,CN4 | KF2EDGV-2.54-4P | 4-pin | UART级联接口 |
| H5 | B-2100S04P-A110 | 4-pin | SWD调试接口 |

### Power
- **Supply voltage**: +12V (来自CN1/CN2)
- **Regulator**: U2-1 (XC6206P332MR-G, SOT-23-3) → 3.3V LDO
- **Isolated power**: U1-1 (VPS8701B) + T1-1 (VPT87DFB01B) → 隔离电源
- **稳压参考**: U1 (TLV431A) → 产生1.65V参考电压 (通过R3=660Ω, R4=820Ω分压)
- **Power domains**: 3.3V (数字), 3.3VA (模拟隔离侧), 5V, 5VA, ISOGND (隔离地)

### Connectors
- **CN1/CN2**: 电池连接端子 (2-pin, 3.96mm间距) — +12V, GND
- **CN3/CN4**: UART级联接口 (4-pin, 2.54mm间距, xh2_54-4p) — 信号定义见网表
- **H5**: SWD调试接口 (4-pin, 2.54mm) — SWDIO, SWCLK, 3.3V, GND
- **H6**: DS18B20接口 (3-pin, xh2_54-3p) — DQ, GND, 3.3V
- **H1-H4**: 电池板连接测试点 (battery_pin) — RES_SENSOR+, RES_SENSOR- 等

### Uncertainties
1. **MCU引脚功能映射**: 网表使用U3-1.x (x=1..20) 直接表示TSSOP20物理引脚编号。但标准STM32G030F6P6的TSSOP20引脚功能分配与网表中的功能信号（如UART1_TX在pin20, UART1_RX在pin1）需要对照datasheet确认。从map文件推断之前的main.c使用了 `huart1`、`huart2`、`htim3`、`htim14`、`hadc1`、`hdma_adc1` 等句柄。
2. **ADC通道分配**: VOLT_ADC(MCU pin8)、CURRENT_ADC(MCU pin13)、RES_ADC(MCU pin14) 分别连接到哪些ADC内部通道取决于MCU引脚的实际ADC_IN编号。需要根据最终确定的引脚功能配置ADC通道。
3. **U11/U10型号**: BOM中U8/U9/U10/U11的型号未标注，仅知为SOP-8封装的运放。功能上U10处理RES_ADC信号，U11处理CURRENT_ADC信号。
4. **隔离器U5**: CA-IS3721LS为数字隔离器，具体通道方向配置需参考其数据手册（网表显示: U5.1→CN3.1, U5.2→CN3.2, U5.3→CN3.3, U5.4→CN3.4, U5.6→UART2_TX, U5.7→UART2_RX）。
5. **TIM14的用途**: 中断已使能但未明确分配信号。可能用于定时/调度或DS18B20时序控制。

## Build, Flash, And Run Notes

- **Build system**: Keil MDK-ARM (UV4)
- **IDE project**: `battery_re/MDK-ARM/battery_re.uvprojx`
- **Toolchain**: ArmClang V6.19 (ARM-ADS), Cortex-M0+
- **Build command**: `C:\Keil_v5\UV4\UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`
- **Exit codes**: 0=成功, 1=有警告(仍通过), 2-20=编译错误, 21+=致命错误
- **Flash command** (provided): `pyocd flash -t stm32f103c8 build/firmware.elf` — **注意**: 目标器件应为 `stm32g030f6` 而非 `stm32f103c8`，路径需调整
- **Serial**: COM3, 115200 baud (根据hardware_config)
- **Host test**: `python host_tests/smoke_test.py --port COM7 --baud 115200`
- **Output artifacts**: `battery_re/MDK-ARM/battery_re/battery_re.axf`, `.hex`, `.bin`
- **Linker script**: 内置散列文件 (scatter)，IROM=0x08000000/64KB, IRAM=0x20000000/8KB
- **Source directories** (已配置): `../Core/Inc`, `../Drivers/STM32G0xx_HAL_Driver/Inc`, `../Drivers/STM32G0xx_HAL_Driver/Inc/Legacy`, `../Drivers/CMSIS/Device/ST/STM32G0xx/Include`, `../Drivers/CMSIS/Include`, `..\Drivers\CMSIS\DSP\Include`
- **Preprocessor defines**: `USE_HAL_DRIVER`, `STM32G030xx`
- **HAL modules enabled**: ADC, TIM, UART, GPIO, EXTI, DMA, RCC, FLASH, PWR, CORTEX, IWDG

### Files that exist but need creation
- `Core/Src/main.c` — **缺失**, 需创建 (含外设初始化、SystemClock_Config、主状态机)
- `Core/Src/stm32g0xx_hal_msp.c` — **缺失**, 需创建 (HAL MSP初始化)

### Files that exist and are ready
- `Core/Src/stm32g0xx_it.c` — 中断框架 (已含SCHED_IncTick和UART_IRQHandler弱符号)
- `Core/Src/system_stm32g0xx.c` — 系统时钟配置 (64MHz)
- `Core/Inc/stm32g0xx_hal_conf.h` — HAL配置
- `Core/Inc/stm32g0xx_it.h` — 中断声明
- `MDK-ARM/startup_stm32g030xx.s` — 启动文件

## Constraints And Risks

### Missing information
- main.c 和 stm32g0xx_hal_msp.c 已被删除，需要从零重构。
- UART通信协议自定义，未提供具体帧格式。
- 校准算法（相位校正、多点电阻校正）需自行设计。
- 异常数据识别算法需自行设计。
- 注入电流的幅值设定方式未明确（PWM占空比可调范围？）。

### Unclear hardware details
- MCU TSSOP20引脚与GPIO/外设功能的精确映射需要核对datasheet Section 4 (Pinouts)。datasheet PDF解析不完全，部分表格信息丢失。
- U10/U11运放型号未知，其增益/带宽参数不确定。
- RC滤波器截止频率未明确（R21=100K, C14=1nF → fc≈1.6kHz，产生1kHz正弦波需确认）。
- 恒流源电路增益未明确。

### Uncertain build or flash commands
- flash命令中的目标器件 `stm32f103c8` 与实际MCU `STM32G030F6P6` 不符，需要修正。
- pyOCD对STM32G030的支持需确认。

### Incomplete acceptance criteria
- 未定义具体的内阻测量精度要求。
- 未定义UART协议的具体数据格式。
- 未定义校准流程和验收标准。

### Truncated or unreadable files
- `__ds12991_tmp.txt` 和 `__out1.txt` 是datasheet的截取片段，内容不完整。
- `DS12991/document.md` (298913行) 为完整PDF转换，但表格格式混乱，引脚信息需要仔细核对。

### Real-hardware verification risks
- 硬件可能尚未组装或调试，无法进行实际内阻测量验证。
- 级联通信需要多个电池板同时工作才能完整测试。

## Confidence Assessment

| Section | Confidence | Reason |
|---------|-----------|--------|
| Goal | High | 用户需求清晰，功能描述详细，目标明确 |
| Task Requirements | High | user_req.txt完整描述了19条功能和实现要求 |
| Hardware Connection | Medium | 网表提供了完整的连接信息，但MCU TSSOP20引脚到GPIO功能的映射需要datasheet交叉验证，部分芯片型号未知 |
| Build & Flash | High | Keil项目配置已验证（成功编译），编译命令明确，flash命令需修正目标器件 |
| Constraints & Risks | Medium | 主要风险在于缺失的main.c/MSP需要重构、自定义协议需设计、校准算法需开发，以及硬件可能未经调试 |
```