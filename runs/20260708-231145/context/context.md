Now I have enough information. Let me write the context.md.

```markdown
# Build Context

## Goal

基于 STM32G030F6P6 (TSSOP-20) 实现电池内阻测量系统。使用 PWM 产生 1kHz 方波，经 RC 滤波形成正弦波，通过恒流源向电池注入交流电流，同步采集电池两端电压，计算内阻。系统支持 DS18B20 温度测量 (30s 周期)、UART 级联多机通讯（主/从模式，自定义协议）、定时内阻测量（每 1 分钟）。全部采用状态机架构，禁止阻塞。要求输出完整工程代码到 `battery_re` 目录，使用 Keil MDK-ARM 编译通过。

## Source Materials

### Directory Overview

| 目录 | 说明 |
|------|------|
| `battery_re/` | 目标工程根目录，包含现有骨架代码 |
| `battery_re/Core/Inc/` | 用户头文件：stm32g0xx_hal_conf.h, stm32g0xx_it.h |
| `battery_re/Core/Src/` | 用户源文件：stm32g0xx_it.c, system_stm32g0xx.c (main.c 和 hal_msp.c 尚不存在) |
| `battery_re/Drivers/CMSIS/` | CMSIS 核心、Device、DSP 库 |
| `battery_re/Drivers/STM32G0xx_HAL_Driver/` | STM32G0 HAL 驱动 (Inc + Src) |
| `battery_re/MDK-ARM/` | Keil 项目文件 (uvprojx)、启动文件、编译日志 |
| `.document-reader/` | 文档资料：网表 (netlist)、BOM、DS12991 数据手册 |
| `.understand-anything/` | 结构分析中间输出 (JSON) |

### Key Files Inspected

- `user_req.txt` — 用户需求文档，包含完整功能描述、引脚分配、通讯协议设计要求
- `Netlist_Schematic1_2026-05-25.tel` — 原始网表文件，包含所有网络连接
- `.document-reader/netlist/document.md` — 网表 Markdown 版本，列出全部信号连接
- `.document-reader/BOM/document.md` — BOM 物料清单 (同 xlsx 转换)
- `.document-reader/BOM_Board1_Schematic1_2026-05-23/document.md` — 另一份 BOM 副本
- `.document-reader/DS12991/chunks/chunk_0036-0043.md` — DS12991 数据手册片段（引脚分配、复用功能表）
- `__ds12991_tmp.txt` — DS12991 数据手册临时文件（TOC 和特性概述）
- `battery_re/MDK-ARM/battery_re.uvprojx` — Keil 项目配置：Device=STM32G030F6Px, RAM 8KB, Flash 64KB, ARMCLANG V6.19
- `battery_re/MDK-ARM/startup_stm32g030xx.s` — 启动文件 (Stack 0x400, Heap 0x200)
- `battery_re/Core/Inc/stm32g0xx_hal_conf.h` — HAL 模块配置：已使能 ADC, TIM, UART, GPIO, EXTI, DMA, RCC, FLASH, PWR, IWDG
- `battery_re/Core/Inc/stm32g0xx_it.h` — 中断声明: DMA1_Ch1, ADC1, TIM1_BRK_UP_TRG_COM, TIM3, TIM14, USART1, USART2
- `battery_re/Core/Src/stm32g0xx_it.c` — 中断实现，包含弱符号存根 SCHED_IncTick() 和 UART_IRQHandler()
- `battery_re/Core/Src/system_stm32g0xx.c` — 系统时钟配置：HSE 8MHz → PLL → 64MHz SysClk
- `battery_re/MDK-ARM/build_log.txt` — 成功编译日志 (0 Error, 0 Warning)

## Task Requirements

### Functional behavior
- 使用 PWM (TIM3_CH3) 产生 1kHz 占空比 50% 方波 → RC 滤波器形成正弦波 → 跟随器 → 运放恒流源 → 注入电池
- 通过采样电阻 (R16, 0.1Ω) 测量注入电流
- 同步采集电池两端电压 (10kHz 采样率，与电流相位同步)
- 计算电池内阻：R = V_measured / I_injected
- 对电路引起的相位差进行软件校正
- 使用实际电阻进行多点校准
- DS18B20 温度测量 (30s 周期)
- 定时内阻测量（每 1 分钟）
- 异常数据识别算法（抗充电/放电干扰）
- 全部使用状态机，禁止阻塞

### Interfaces and protocols
- **USART1** (主机): PA9(TX), PA10(RX) — 与下一个从机通讯，发送指令并接收数据
- **USART2** (从机): PA2(TX), PA3(RX) — 接收前级主机指令
- 级联通讯：一组电池中只有一个主机，其余为从机。主机分配地址，定时轮询所有从机数据
- 自定义 UART 级联协议，主机收集所有从机的电压、电流、内阻、温度等数据
- DS18B20: 单总线 (DQ pin)，30s 测量一次

### Outputs and indicators
- 主机通过 USART1 向上位机/下一级发送采集数据（电压、注入电流、内阻、温度）
- [推断] 主机开机后分配从机地址，定期轮询

### Timing and performance
- PWM 频率: 1kHz (TIM3_CH3)
- ADC 采样率: 10kHz (与电流相位同步)
- 温度测量: 30s 周期
- 内阻测量: 1 分钟周期
- 系统时钟: 64MHz

### Tests and acceptance criteria
- 编译通过 (0 Error, 0 Warning)
- 设计文档与代码同样重要
- 需要输出通讯协议设计方案

## Hardware Connection

### MCU / SoC
- **Part number**: STM32G030F6P6TR (STM32G030F6P6)
- **Core / architecture**: ARM Cortex-M0+, 32-bit, up to 64 MHz
- **Package**: TSSOP-20 (6.4×4.4 mm)
- **Flash**: 64 KB (0x08000000, 0x10000)
- **SRAM**: 8 KB (0x20000000, 0x2000)

### Debug / Flash Interface
- **Protocol**: Serial Wire Debug (SWD)
- **Connector**: H5 (4-pin header, B-2100S04P-A110)
  - H5.1 = 3.3V
  - H5.2 = GND (ISOGND)
  - H5.3 = SWDIO (MCU pin 18)
  - H5.4 = SWCLK (MCU pin 19)
- **Required tools**: J-Link / ST-Link / pyOCD

### Peripheral Wiring

| 信号 | MCU Pin# | TSSOP20 Pin | GPIO/AF | 目标器件/模块 | 方向 | 备注 |
|------|----------|-------------|---------|-------------|------|------|
| UART1_TX | PA9 | 20 | AF1 (USART1_TX) | 下一级从机/主机 | 输出 | 级联主机发送 |
| UART1_RX | PA10 | 1 | AF1 (USART1_RX) | 下一级从机/主机 | 输入 | 级联主机接收 |
| UART2_TX | PA2 | 9 | AF1 (USART2_TX) | 前级主机 | 输出 | 级联从机发送 |
| UART2_RX | PA3 | 10 | AF1 (USART2_RX) | 前级主机 | 输入 | 级联从机接收 |
| TIM3_CH3 | PB0 | 15 | AF1 (TIM3_CH3) | RC滤波器 → 恒流源 | 输出 | 1kHz PWM 方波 |
| VOLT_ADC | PA1 | 8 | ADC_IN1 | 电池电压调理输出 | 输入 | 采集电池两端电压 |
| CURRENT_ADC | PA6 | 13 | ADC_IN6 | 电流检测运放输出 | 输入 | 采样电阻(0.1Ω)两端电压 |
| RES_ADC | PA7 | 14 | ADC_IN7 | [推断] 内阻校准电压 | 输入 | 用于内阻计算 |
| DQ | PA4 | 11 | GPIO | DS18B20 数据线 (H6.2) | 双向 | 4.7kΩ (R6) 上拉到 3.3V |
| M_S | PA5 | 12 | GPIO | 主从选择 (R9 上拉) | 输入 | 高=主机，低=从机 |
| NRST | NRST | 6 | - | 外部复位电路 (U6) | 输入 | 内置弱上拉 |
| SWDIO | PA13 | 18 | SWDIO | H5.3 (调试接口) | 双向 | 复位后默认 SWD |
| SWCLK | PA14 | 19 | SWCLK | H5.4 (调试接口) | 输入 | 复位后默认 SWD |

### Power

| 网络 | 电压 | 来源 | 说明 |
|------|------|------|------|
| +12V | 12V | CN1/CN2 (外部电源) | 主电源输入 |
| 5V | 5V | [推断] 经 D2-1/D3-1 整流 | 来自隔离电源 |
| 5VA | 5V | [推断] 经 R2 从 5V 派生 | 模拟供电 |
| 3.3V | 3.3V | U2-1 (XC6206P332MR-G, LDO) | MCU 数字供电 |
| 3.3VA | 3.3V | [推断] 从 5VA 经 R1/R3 分压 | 模拟供电 |
| 1.65V | 1.65V | 由 R3(660Ω)/R4(820)/R5(2.49k) 分压 + U1(TLV431) 稳压 | ADC 参考/偏置 |
| GND | 0V | CN1/CN2 | 电源地 |
| ISOGND | 0V | 隔离地 | 所有 MCU 和模拟电路地 |

- **Regulator / LDO**: XC6206P332MR-G (3.3V 输出, SOT-23-3)
- **Isolated DC-DC**: VPS8701B (SOT-23-6) + T1-1 变压器
- **Voltage reference**: TLV431AIDBZR (可调分流基准, 用于 1.65V)

### Key Circuit Blocks (from netlist analysis)

1. **交流恒流源链路**: TIM3_CH3(PB0) → R21(100K) → RC滤波器(C7+R20+R19+...) → [推断] LM258(OP1) 跟随器 → 运放(U8/U9)恒流源 → 电池
2. **电流检测**: R16(0.1Ω 采样电阻) → [推断] 差分放大(U9) → CURRENT_ADC(PA6)
3. **电压检测**: 电池两端 → [推断] 差分放大(U10) → VOLT_ADC(PA1)
4. **隔离**: U5(CA-IS3721LS) 数字隔离器 — 用于 UART 隔离
5. **DS18B20**: H6(3-pin) 连接器, DQ 经 R6(4.7k) 上拉到 3.3V
6. **RS485 连接器**: CN3/CN4 (4-pin) — 用于 UART 级联通讯
7. **电池连接**: H1/H2/H3/H4 (battery_pin 封装) — RES_SENSOR+/RES_SENSOR-

## Uncertainties

- TSSOP20 引脚 2 (PC14/OSC32_IN) 和引脚 3 (PC15/OSC32_OUT) 在网表中未明确标注连接，[推断] 可能未使用或作为 GPIO
- 引脚 16 (PB1) 和引脚 17 (PB2) 在网表中未出现，可能未连接
- U8/U9/U10/U11 的具体型号未在 BOM 中明确给出（SOP-8 封装），[推断] 为运算放大器或模拟开关
- 相位差校正的具体电路参数（RC 滤波器截止频率等）未明确给出，需根据实际电路测量
- 异常数据识别算法无具体定义，需自行设计
- UART 级联通讯协议未定义，需自定义

## Build, Flash, And Run Notes

- **Build system**: Keil MDK-ARM (µVision)
- **Build command**: `C:\Keil_v5\UV4\UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`
- **Compiler**: ArmClang V6.19 (ARMCC)
- **Preprocessor defines**: `USE_HAL_DRIVER,STM32G030xx`
- **Include paths**: `../Core/Inc;../Drivers/STM32G0xx_HAL_Driver/Inc;../Drivers/STM32G0xx_HAL_Driver/Inc/Legacy;../Drivers/CMSIS/Device/ST/STM32G0xx/Include;../Drivers/CMSIS/Include;..\Drivers\CMSIS\DSP\Include`
- **Working directory**: `C:\Users\123\Desktop\neizu\tasknew\battery_re`
- **Output artifacts**: `battery_re/battery_re.axf` (ELF), `battery_re/battery_re.hex`
- **Flash command**: `pyocd flash -t stm32f103c8 build/firmware.elf` (注：pyOCD target 名可能需改为 stm32g030f6p6)
- **Serial/debug**: COM3 (115200, 8N1), host test: `python host_tests/smoke_test.py --port COM7 --baud 115200`

### Existing Project Files (骨架)

| 文件 | 状态 | 内容 |
|------|------|------|
| `Core/Src/main.c` | ❌ 不存在 | 需要创建 |
| `Core/Src/stm32g0xx_it.c` | ✅ 存在 | 中断服务 + 弱符号存根 |
| `Core/Src/stm32g0xx_hal_msp.c` | ❌ 不存在 | 需要创建 (HAL MSP 初始化) |
| `Core/Src/system_stm32g0xx.c` | ✅ 存在 | 时钟 64MHz 配置 |
| `Core/Inc/stm32g0xx_hal_conf.h` | ✅ 存在 | HAL 模块选择 |
| `Core/Inc/stm32g0xx_it.h` | ✅ 存在 | 中断声明 |
| `MDK-ARM/startup_stm32g030xx.s` | ✅ 存在 | 启动文件 |
| `MDK-ARM/battery_re.uvprojx` | ✅ 存在 | Keil 项目配置 |

## Constraints And Risks

- **Missing information**: 
  - main.c 和 stm32g0xx_hal_msp.c 需要从头创建
  - UART 级联通讯协议完全未定义
  - 异常数据识别算法未指定
  - 相位校正算法未指定
  - 多点校准方案未指定
  
- **Unclear hardware details**:
  - TSSOP20 引脚 16/17 (PB1/PB2) 未使用，可作为通用 GPIO 或悬空
  - U8/U9/U10/U11 型号未确认（SOP-8，可能是 LMV324 或类似运放）
  - RC 滤波器的具体截止频率未知（R20/R19/C6/C7 等参数已知，但连接拓扑需推断）
  
- **Uncertain build or flash commands**:
  - pyOCD flash 命令中的 target `stm32f103c8` 与 MCU (STM32G030F6P6) 不匹配，需确认
  - Keil UV4 的退出码需处理（0=成功, 1=有warning, 2+=error）
  
- **Incomplete acceptance criteria**:
  - 无具体的测试固件验证方案
  - 无硬件验证计划（如信号完整性、精度指标）
  
- **Real-hardware verification risks**:
  - 通讯协议错误可能导致多机通讯失败
  - 相位同步采集需要精确的定时控制
  - 异常数据识别在不干扰正常数据的情况下实现困难

## Confidence Assessment

| 部分 | 置信度 | 原因 |
|------|--------|------|
| Goal | High | 用户需求文档完整描述了系统功能和目标 |
| Task Requirements | High | 需求文档清晰，功能、接口、时序均有说明 |
| Hardware Connection | Medium | 网表提供了完整连接信息，但 TSSOP20 引脚号与 GPIO 的映射从数据手册中部分推断，且 U8-U11 型号未知 |
| Build & Flash | Medium | Keil 项目配置完整且已验证编译通过，但 pyOCD flash 命令的 target 名称可能不匹配 |
| Constraints & Risks | High | 缺失部分（main.c, hal_msp.c, 协议等）已明确识别 |
```