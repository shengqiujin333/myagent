Now I have enough information. Let me write the context.md.

```markdown
# Build Context

## Goal

本项目的目标是开发一套**电池内阻测量系统**的嵌入式固件，基于 **STM32G030F6P6** (TSSOP-20) 微控制器，完成以下核心功能：

- 通过 PWM (TIM3_CH3) 产生 1kHz 方波，经 RC 滤波 → 跟随器 → 运放恒流源，向电池注入交流电流
- 以 10kHz 采样率、与电流相位同步的方式采集电池两端电压，计算电池内阻
- 支持多点校准：对注入电流和采集电压与实际电阻进行校准
- 对充电/放电产生的干扰数据进行异常识别和剔除
- 每 1 分钟测量一次内阻，每 30 秒通过 DS18B20 (DQ) 测量一次温度
- 多电池手拉手级联通讯：UART2 作为从机接收前级主机指令，UART1 作为主机向后级从机发送指令
- 主机可动态分配从机地址，轮询读取所有从机的电压、电流、内阻、温度等数据
- 主机/从机通过引脚 M_S (pin 12) 电平判断：上拉输入，高电平=主机，低电平=从机
- 全部逻辑使用状态机实现，禁止阻塞
- 协议自定义（UART 级联通讯协议）

## Source Materials

### Directory Overview

| Directory | Summary |
|-----------|---------|
| `battery_re/Core/Inc/` | 现有头文件：`stm32g0xx_hal_conf.h` (HAL配置，已启用ADC/TIM/UART/DMA/IWDG/EXTI)，`stm32g0xx_it.h` (中断声明) |
| `battery_re/Core/Src/` | 现有源文件：`stm32g0xx_it.c` (中断向量实现，含弱符号存根 SCHED_IncTick, UART_IRQHandler)，`system_stm32g0xx.c` (系统初始化，64MHz时钟配置) |
| `battery_re/Drivers/STM32G0xx_HAL_Driver/` | STM32G0 HAL 驱动库 (Inc + Src) |
| `battery_re/Drivers/CMSIS/` | CMSIS 核心、设备、DSP 库 (含 arm_cortexM0l_math.lib) |
| `battery_re/MDK-ARM/` | Keil MDK-ARM 项目文件 (uvprojx)，启动文件 `startup_stm32g030xx.s`，构建日志 |
| `.document-reader/` | 硬件文档的 markdown 提取：MCU 数据手册(DS12991)、网表文件、BOM 文件 |
| `.understand-anything/` | 中间处理文件，知识图谱等辅助分析材料 |

### Key Files Inspected

- `user_req.txt` — 用户需求文档，详细描述了功能要求、引脚定义、通讯协议要求、编译方式
- `Netlist_Schematic1_2026-05-25.tel` — 网表文件，定义了所有元器件的网络连接关系
- `.document-reader/DS12991/document.md` — STM32G030x6/x8 数据手册 (DS12991 Rev 6)
- `.document-reader/BOM/document.md` — BOM 清单 (含完整元器件列表)
- `.document-reader/netlist/document.md` — 网表 markdown 格式
- `battery_re/MDK-ARM/battery_re.uvprojx` — Keil 项目文件，定义了源文件组、编译器选项、链接配置
- `battery_re/MDK-ARM/startup_stm32g030xx.s` — 启动文件，堆栈配置 (Stack=0x400, Heap=0x200)，中断向量表
- `battery_re/MDK-ARM/build_log.txt` — 最近成功构建日志 (0 Error, 0 Warning)
- `battery_re/Core/Src/stm32g0xx_it.c` — 中断处理实现，包含弱符号存根函数
- `battery_re/Core/Src/system_stm32g0xx.c` — 系统时钟配置 (HSE 8MHz → PLL → 64MHz SysClk)
- `battery_re/Core/Inc/stm32g0xx_hal_conf.h` — HAL 模块启用配置

## Task Requirements

### Functional behavior
- PWM 产生 1kHz 占空比 50% 方波 → RC 滤波成正弦波 → 恒流源注入电池
- 每 1 分钟测量一次电池内阻
- 每 30 秒通过 DS18B20 测量一次温度
- 10kHz ADC 采样与注入电流相位同步
- 相位差校准：补偿电路导致的注入电流与电压之间的相位偏移
- 多点校准：用实际电阻对测量值进行多点校准
- 异常数据识别算法：排除充电/放电产生的干扰数据

### Interfaces and protocols
- **UART1**: 主机模式，向下级从机发送指令 (TX: U3-1.20, RX: U3-1.1)
- **UART2**: 从机模式，接收上级主机指令 (TX: U3-1.9, RX: U3-1.10)
- **DS18B20**: 单总线协议，引脚 DQ (U3-1.11)
- 自定义 UART 级联通讯协议：主机分配地址、轮询读取数据

### Outputs and indicators
- PWM (TIM3_CH3, U3-1.15): 1kHz 50% 方波
- ADC 采样: VOLT_ADC, CURRENT_ADC, RES_ADC

### Timing and performance
- 系统时钟: 64 MHz (HSE 8MHz → PLL → /1 * 16 /2)
- PWM 频率: 1kHz
- ADC 采样率: 10kHz (与注入电流同步)
- 测量间隔: 1 分钟 (内阻), 30 秒 (温度)
- 全部状态机实现，无阻塞

### Tests and acceptance criteria
- 通过 Keil 编译 (UV4.exe -j0 -b)
- 协议设计文档需输出
- 架构设计和模块划分文档需输出

## Hardware Connection

### MCU / SoC
- **Part number**: STM32G030F6P6 (TSSOP-20, 6.4×4.4 mm)
- **Core**: ARM Cortex-M0+, up to 64 MHz
- **Flash**: 32 KB (STM32G030F6) or 64 KB (STM32G030F8, same part number)
- **SRAM**: 8 KB with HW parity
- **Package pins**: 20 (TSSOP)
- **Ordering code**: STM32G030F6P6TR (tape and reel)

### Debug / Flash Interface
- **Protocol**: Serial Wire Debug (SWD)
- **Connector**: H5 (HDR-TH_4P-P2.54-V-M, B-2100S04P-A110, 4-pin header)
- **Pinout**:
  - Pin 1 (H5.1): 3.3V
  - Pin 2 (H5.2): GND (ISOGND)
  - Pin 3 (H5.3): SWDIO (MCU PA13, pin 18)
  - Pin 4 (H5.4): SWCLK (MCU PA14-BOOT0, pin 19)
- **Flash tool**: pyocd flash -t stm32f103c8 build/firmware.elf (config 中指定，但实际目标为 STM32G030，可能需要调整)

### Peripheral Wiring

| Signal | MCU Pin (TSSOP20) | Target Device / Module | Direction | Notes |
|--------|-------------------|----------------------|-----------|-------|
| UART1_RX | Pin 1 (PB7) | 下一级从机 UART1_TX | Input | 通过 R11 (10Ω) 串联 |
| UART1_TX | Pin 20 (PB3/PB4/PB5/PB6) | 下一级从机 UART1_RX | Output | 通过 R10 (10Ω) 串联 |
| UART2_RX | Pin 10 (PA3) | 上一级主机 UART2_TX | Input | 通过 R7 (10Ω) 串联 |
| UART2_TX | Pin 9 (PA2) | 上一级主机 UART2_RX | Output | 通过 R8 (10Ω) 串联 |
| TIM3_CH3 | Pin 15 (PB0) | RC滤波网络 → 恒流源 | Output | 1kHz 50% PWM 方波 |
| VOLT_ADC | Pin 8 (PA1) | 电压测量调理电路 | Input | ADC 采样电池电压 |
| CURRENT_ADC | Pin 13 (PA6) | 电流测量调理电路 | Input | ADC 采样注入电流 |
| RES_ADC | Pin 14 (PA7) | 电阻测量调理电路 | Input | ADC 采样内阻相关电压 |
| DQ | Pin 11 (PA4) | DS18B20 温度传感器 | Bidir | 4.7kΩ (R6) 上拉到 3.3V，通过 H6 (xh2_54-3p) 连接 |
| M_S | Pin 12 (PA5) | 主从选择 | Input | 内部上拉，高=主机，低=从机，开机判断后改输入 |
| NRST | Pin 6 (NRST) | 外部复位 | Input | 连接到外部复位电路 |
| SWDIO | Pin 18 (PA13) | H5.3 (SWD 调试接口) | Bidir | 调试用 |
| SWCLK | Pin 19 (PA14-BOOT0) | H5.4 (SWD 调试接口) | Input | 调试用 |
| VDD | Pin 4 (VDD/VDDA) | 3.3V 供电网络 | Power | 由 XC6206P332MR-G (U2-1) 稳压输出 |
| VSS | Pin 5 (VSS/VSSA) | GND (ISOGND) | Power | 数字/模拟共地 |
| - | Pin 2 (PB9/PC14-OSC32_IN) | (未连接) | - | [推断] 外部晶振未使用，可能悬空 |
| - | Pin 3 (PC15-OSC32_OUT) | (未连接) | - | [推断] 外部晶振未使用，可能悬空 |

[推断] 未使用的 TSSOP20 引脚 (Pin 2=PB9/PC14, Pin 3=PC15) 根据标准设计建议应外部处理或配置为 GPIO 以节省功耗。

### Power
- **Input**: +12V (来自 CN1/CN2 HT396V-3.96-2P 连接器)
- **Regulator**: U2-1 = XC6206P332MR-G (3.3V LDO, SOT-23-3, TOREX)
- **Isolated power**: U1-1 = VPS8701B (SOT-23-6) + T1-1 = VPT87DFB01B 变压器，产生隔离电源
- **Voltage reference**: U1 = TLV431AIDBZR (可调并联稳压器)，产生 1.65V 参考电压 (通过 R3=660Ω, R4=820Ω 分压)
- **Supply rails**: +12V, 5V, 5VA, 3.3V, 3.3VA, 1.65V (参考电压)
- **Power domains**: 隔离前 (Primary: +12V, 5V, 3.3V) 和 隔离后 (Secondary: ISOGND, 3.3VA, 5VA) 通过 U5 (CA-IS3721LS) 隔离器

### Key Passive Components
- **采样电阻 R16**: 0.1Ω / 0805 (用于电流采样)
- **PWM RC滤波**: R18-R21=100K, C11-C14=1nF (四阶 RC 滤波网络，将方波转正弦波)
- **DS18B20 上拉**: R6 = 4.7kΩ
- **UART 串联电阻**: R7, R8, R10, R11 = 10Ω
- **M_S 上拉**: R9 = 100kΩ (内部上拉也启用)

### Uncertainties
- U3-1.7 (MCU pin 7) 在网表中标注为 ISOGND，但 TSSOP20 封装 pin 7 是 PA0，非 GND。可能为网表错误或 PA0 被配置为 GPIO 输出低电平作虚拟地。[推断] 如果是实际连接的 GND，需要在原理图中确认是否通过外部电路连接到地。
- U8, U9, U10, U11 为 SOP-8 封装但未标注型号，从连接推测可能为双运放 (如 LMV358 或其他通用运放)
- OP1 (LM258DT) 可能用于电压跟随器或差分放大

## Build, Flash, And Run Notes

### Build System
- **IDE/Toolchain**: Keil MDK-ARM V5, ArmClang V6.19 (ARMCLANG)
- **Project file**: `MDK-ARM/battery_re.uvprojx`
- **Build command**: `C:\Keil_v5\UV4\UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`
- **Exit codes**: 0=成功, 1=有警告(仍通过), 2-20=编译错误, 21+=致命错误
- **Output directory**: `battery_re\` (相对于 MDK-ARM)

### Compiler Defines
- `USE_HAL_DRIVER`, `STM32G030xx`

### Include Paths
- `../Core/Inc`
- `../Drivers/STM32G0xx_HAL_Driver/Inc`
- `../Drivers/STM32G0xx_HAL_Driver/Inc/Legacy`
- `../Drivers/CMSIS/Device/ST/STM32G0xx/Include`
- `../Drivers/CMSIS/Include`
- `..\Drivers\CMSIS\DSP\Include`

### Memory Map
- **Flash (IROM)**: 0x08000000, 64 KB (0x10000)
- **SRAM (IRAM)**: 0x20000000, 8 KB (0x2000)
- **Stack**: 0x400 (1 KB)
- **Heap**: 0x200 (512 B)

### Output Artifacts
- `battery_re/battery_re.axf` (ELF)
- `battery_re/battery_re.hex` (Intel HEX)
- `battery_re/battery_re.htm` (build report)

### HAL Modules Enabled (from stm32g0xx_hal_conf.h)
- ADC, TIM, UART, GPIO, EXTI, DMA, RCC, FLASH, PWR, CORTEX, IWDG

### Enabled Interrupts (from stm32g0xx_it.h)
- DMA1_Ch1, ADC1, TIM1_BRK_UP_TRG_COM, TIM3, TIM14, USART1, USART2

### Flash / Debug
- Flash driver: `STM32G0xx_32.FLM` (STM32G0xx 32KB flash)
- SVD: `STM32G030.svd`
- pyOCD target: config 指定 `stm32f103c8`，但实际应为 `stm32g030f6`，可能需要调整

### Serial Monitor
- Port: COM3 (config)
- Baud rate: 115200
- Timeout: 30s

### Host Test
- `python host_tests/smoke_test.py --port COM7 --baud 115200`

## Constraints And Risks

### Missing information
- **main.c 和 stm32g0xx_hal_msp.c 不存在**: 项目要求重构全部代码，这两个核心文件需要从零编写
- **通讯协议未定义**: 需要自定义 UART 级联协议（地址分配、数据帧格式、轮询机制）
- **校准算法未指定**: 需要设计多点校准和相位补偿算法
- **异常数据识别算法未指定**: 需要设计抗干扰算法

### Unclear hardware details
- U3-1.7 标注为 GND 但与 TSSOP20 pin 7 (PA0) 矛盾，可能 PA0 用于其他目的
- U8-U11 型号未知（SOP-8），但从连接推断可能为双运放，配置为滤波器/放大器
- 隔离器 U5 (CA-IS3721LS) 的具体连接未详细分析

### Uncertain build or flash commands
- pyOCD flash 命令中的 target `stm32f103c8` 与实际 MCU (STM32G030F6P6) 不匹配，可能需要改为 `stm32g030f6`
- 确认 Keil UV4 的路径和 -j0 参数（已在 user_req.txt 中明确指定）

### Incomplete acceptance criteria
- 验收标准未明确量化（如内阻测量精度、通讯速率等）
- 多点校准的具体点数和方法未指定
- 异常数据识别算法的通过标准未定义

### Real-hardware verification risks
- 多电池级联通讯需要多块硬件互联才能完整测试
- 注入电流与 ADC 采样的相位同步受电路实际参数影响，可能需要调试
- 充电/放电干扰场景难以在开发环境中模拟

## Confidence Assessment

| Section | Confidence | Reason |
|---------|-----------|--------|
| Goal | High | 用户需求文档非常详细，列出了 20 条具体要求和实现步骤 |
| Task Requirements | High | 需求明确、完整，包含功能、接口、时序等各维度 |
| Hardware Connection | Medium | MCU 引脚连接基本明确，但 U3-1.7 存在矛盾，U8-U11 型号未知 |
| Build & Flash | High | 现有项目文件完整，构建日志显示编译通过，命令已验证 |
| Constraints & Risks | Medium | 主要风险是缺失的 main.c 和通讯协议需要从头设计，以及 flash 命令的 target 可能不匹配 |
```